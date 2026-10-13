"""Image candidates: signed on the way out, fetched only with their token."""

import copy
import io
import os
import stat

import pytest
from PIL import Image

from tests.gpubox.spec import validator
from visualizer.gpu_worker.fetch import FetchError
from visualizer.gpu_worker.images import TokenSigner, load_signing_key, to_image

from .conftest import AUTH, RESEARCH_JOB, RESEARCH_RESULT, picture

URL = "https://museum.example/tea-bowl.png"


def ask(client, body):
    return client.post("/v1/images", json=body, headers=AUTH)


def documented_error(response, status, code):
    assert response.status_code == status, response.get_data(as_text=True)
    validator("ErrorResponse").validate(response.get_json())
    assert response.get_json()["error"]["code"] == code
    return response.get_json()["error"]


# -- fetching ----------------------------------------------------------------


def test_a_signed_candidate_comes_back_as_its_image(client, web, signer):
    original = picture(800, 600)
    web.pages[URL] = original
    response = ask(client, {"url": URL, "token": signer.sign(URL)})
    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert response.data == original, "full size is the original bytes, untouched"


def test_a_preview_is_small_and_re_encoded(client, web, signer):
    web.pages[URL] = picture(1600, 1200)
    response = ask(client, {"url": URL, "token": signer.sign(URL), "size": "preview"})
    assert response.content_type == "image/jpeg"
    with Image.open(io.BytesIO(response.data)) as preview:
        assert max(preview.size) == 360


def test_a_transparent_preview_stays_png(client, web, signer):
    web.pages[URL] = picture(500, 500, mode="RGBA")
    response = ask(client, {"url": URL, "token": signer.sign(URL), "size": "preview"})
    assert response.content_type == "image/png"


@pytest.mark.parametrize("token", ["x" * 43, "short", None])
def test_without_its_own_token_nothing_is_fetched(client, web, signer, token):
    web.pages[URL] = picture()
    body = {"url": URL, "token": token} if token else {"url": URL}
    documented_error(ask(client, body), 400, "invalid_request")
    assert web.asked == []


def test_a_token_opens_only_its_own_url(client, web, signer):
    other = "http://169.254.169.254/latest/meta-data/"
    documented_error(ask(client, {"url": other, "token": signer.sign(URL)}), 400,
                     "invalid_request")
    assert web.asked == []


@pytest.mark.parametrize("page,message", [
    (None, "The source answered 404"),
    (FetchError("blocked", "Refused: the source is not a public address"),
     "Refused: the source is not a public address"),
    ((b"<html>not an image</html>", "text/html"), "Not an image the worker can read"),
])
def test_an_image_that_cannot_be_had(client, web, signer, page, message):
    if page is not None:
        web.pages[URL] = page
    error = documented_error(ask(client, {"url": URL, "token": signer.sign(URL)}),
                             502, "image_unavailable")
    assert error["message"] == message


def test_unsupported_formats_and_bombs_are_refused():
    tiff = io.BytesIO()
    Image.new("RGB", (10, 10)).save(tiff, "TIFF")
    with pytest.raises(FetchError, match="Not a supported image format"):
        to_image(tiff.getvalue(), "full")
    with pytest.raises(FetchError, match="Not an image"):
        to_image(picture(8000, 6000), "full")   # 48 Mpx, over the 40 Mpx cap


# -- signing -----------------------------------------------------------------


def test_the_runner_signs_every_candidate_and_overwrites_forgeries(
        client, runner, pipelines, signer):
    result = copy.deepcopy(RESEARCH_RESULT)
    result["article"]["image_candidates"] = [
        {"url": URL, "source": "s1", "caption": "A bowl", "license": None},
        {"url": URL + "?2", "source": "s1", "caption": "Another", "license": None,
         "fetch_token": "f" * 43},
    ]
    pipelines.behaviour = lambda request, ctx: result
    job_id = client.post("/v1/jobs", json=RESEARCH_JOB, headers=AUTH
                         ).get_json()["job"]["id"]
    runner.run_next()
    job = client.get(f"/v1/jobs/{job_id}", headers=AUTH).get_json()["job"]
    validator("Job").validate(job)
    for candidate in job["result"]["article"]["image_candidates"]:
        assert candidate["fetch_token"] == signer.sign(candidate["url"])


def test_tokens_are_bound_to_one_url_and_one_key():
    one, two = TokenSigner(b"a" * 32), TokenSigner(b"b" * 32)
    token = one.sign(URL)
    assert len(token) == 43
    assert one.verify(URL, token)
    assert not one.verify(URL + "x", token)
    assert not two.verify(URL, token)


def test_the_key_is_generated_once_and_kept_private(tmp_path):
    key_file = tmp_path / "data" / "signing.key"
    first = load_signing_key(None, key_file)
    assert stat.S_IMODE(os.stat(key_file).st_mode) == 0o600
    assert load_signing_key(None, key_file) == first
    assert load_signing_key("from-env", key_file) != first
