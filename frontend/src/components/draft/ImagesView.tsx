import { useState } from "react";
import type { ImageCandidate } from "../../api/types";
import { Icon } from "../ui/Icon";
import type { DraftActions } from "./actions";

/** Openly licensed pictures the researcher found; adding one imports it on save. */
export function ImagesView({
  images,
  draft,
  previewUrl,
  actions,
}: {
  images: ImageCandidate[];
  draft: string;
  previewUrl: (index: number) => string;
  actions: DraftActions;
}) {
  // A preview the box could not fetch means the picture is gone from the web,
  // and importing it on save would fail too.
  const [gone, setGone] = useState<ReadonlySet<number>>(new Set());
  const markGone = (index: number) => setGone((prev) => new Set(prev).add(index));

  return (
    <ul className="st-images">
      {images.map((image) => (
        <ImageItem
          key={image.index}
          image={image}
          url={previewUrl(image.index)}
          added={actions.hasImage(draft, image.index)}
          gone={gone.has(image.index)}
          onGone={() => markGone(image.index)}
          onAdd={(url) =>
            actions.addImage({
              draft,
              index: image.index,
              caption: image.caption,
              previewUrl: url,
              mediaId: image.imported,
            })
          }
        />
      ))}
    </ul>
  );
}

function ImageItem({
  image,
  url,
  added,
  gone,
  onGone,
  onAdd,
}: {
  image: ImageCandidate;
  url: string;
  added: boolean;
  gone: boolean;
  onGone: () => void;
  onAdd: (url: string) => void;
}) {
  return (
    <li className={`st-image${added ? " is-added" : ""}${gone ? " is-gone" : ""}`}>
      <div className="st-image-frame">
        {gone ? (
          <p className="st-image-gone">
            <Icon name="alert" size={16} /> This picture is no longer on the web.
          </p>
        ) : (
          <img src={url} alt={image.caption} loading="lazy" onError={onGone} />
        )}
      </div>
      <p className="st-image-caption">{image.caption || "Untitled image"}</p>
      <p className="st-image-license">{image.license ?? "Licence unknown"}</p>
      <button
        type="button"
        className="st-btn st-btn-secondary st-btn-sm"
        disabled={added || gone}
        onClick={() => onAdd(url)}
      >
        <Icon name={added ? "check" : gone ? "ban" : "plus"} size={14} />{" "}
        {added ? "In note" : gone ? "Not available" : "Add to note"}
      </button>
    </li>
  );
}
