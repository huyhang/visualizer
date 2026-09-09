// A voxel diorama, rendered in place: a still scene on a slowly turning camera.
//
// Two things here are deliberate and easy to get wrong the other way.
//
// **The camera orbits; the model does not.** Turning the model sweeps its
// shadow across the ground with it, which reads as the world spinning under a
// fixed sun. Orbiting the camera leaves the sun where it is, so the shadow
// stays put and the scene looks lit rather than animated.
//
// **Only a few scenes may be live at once.** Every viewer holds a WebGL
// context and browsers cap those at roughly eight to sixteen, silently
// dropping the oldest past the limit. So viewers mount when they scroll into
// view, and a pool retires the least recently seen one rather than letting the
// browser decide which article figure goes blank.

import * as THREE from "./vendor/three/three.module.min.js";
import { GLTFLoader } from "./vendor/three/GLTFLoader.js";
import { OrbitControls } from "./vendor/three/OrbitControls.js";

const MAX_LIVE_SCENES = 4;
const live = new Set();

function retireOldest() {
  while (live.size >= MAX_LIVE_SCENES) {
    const oldest = live.values().next().value;
    if (!oldest) break;
    oldest.sleep();
  }
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
}

export function webglAvailable() {
  try {
    const probe = document.createElement("canvas");
    return Boolean(probe.getContext("webgl2") || probe.getContext("webgl"));
  } catch {
    return false;
  }
}

// A scene that has been built and is holding a context. Kept separate from the
// mount below so `sleep()` can give the context back without forgetting how to
// build it again.
class Stage {
  constructor(host, model, manifest, { capture = false } = {}) {
    this.host = host;
    this.manifest = manifest;
    this.disposed = false;

    // `preserveDrawingBuffer` costs a little performance, so it is on only in
    // the editor, where the point is to read the pixels back as a poster.
    this.renderer = new THREE.WebGLRenderer({
      antialias: true, alpha: true, preserveDrawingBuffer: capture,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    host.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.1, 2000);

    const bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3());
    const centre = bounds.getCenter(new THREE.Vector3());
    model.position.sub(centre.clone().setY(bounds.min.y));
    model.traverse((node) => {
      if (node.isMesh) { node.castShadow = true; node.receiveShadow = true; }
    });
    this.scene.add(model);
    this.model = model;

    this._addGround(size);
    this._addSun(size);
    this._addLocalLights();
    this._frame(size);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.enablePan = false;
    this.controls.target.set(0, size.y * 0.4, 0);
    this.controls.autoRotate = manifest.auto_rotate && !prefersReducedMotion();
    this.controls.autoRotateSpeed = (manifest.rotation_speed ?? 6) / 6;
    this.controls.update();

    this.clock = new THREE.Clock();
    this._onResize = () => this.resize();
    window.addEventListener("resize", this._onResize);
    this.resize();
    this.renderer.setAnimationLoop(() => this._tick());
  }

  _addGround(size) {
    // Three times the footprint: a shadow that runs off the edge of its own
    // ground plane looks like the model is floating.
    const span = Math.max(size.x, size.z, 1) * 3;
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(span, span),
      new THREE.ShadowMaterial({ opacity: 0.28 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    this.scene.add(ground);
    this.ground = ground;
  }

  _addSun(size) {
    // Cool sky above, warm bounce from the ground: the ambient half of the
    // lighting, so shadowed faces read as shaded rather than black.
    this.scene.add(new THREE.HemisphereLight(0xbfd4ff, 0x6b6350, 1.1));
    const sun = new THREE.DirectionalLight(0xfff2dc, 2.4);
    sun.position.set(size.x || 4, Math.max(size.y * 2, 6), size.z || 4);
    sun.castShadow = true;
    // The shadow camera is fitted to the model rather than left at its
    // defaults: a 2048 map spread over a default frustum spends almost all of
    // its resolution on empty ground.
    const span = Math.max(size.x, size.z, 4) * 0.9;
    Object.assign(sun.shadow.camera, {
      left: -span, right: span, top: span, bottom: -span,
      near: 0.5, far: Math.max(size.y * 6, 80),
    });
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0006;
    sun.shadow.camera.updateProjectionMatrix();
    this.scene.add(sun);
    this.sun = sun;
  }

  _addLocalLights() {
    for (const light of this.manifest.lights || []) {
      const colour = new THREE.Color(light.color || "#ffffff");
      const lamp = light.type === "spot"
        ? new THREE.SpotLight(colour, light.intensity ?? 1, 0, Math.PI / 5, 0.4, 1.4)
        : new THREE.PointLight(colour, light.intensity ?? 1, 0, 1.6);
      lamp.position.set(light.x ?? 0, light.y ?? 0, light.z ?? 0);
      this.scene.add(lamp);
    }
  }

  _frame(size) {
    // Distance from the model's own extent, so a small model fills the frame
    // as well as a large one does.
    const reach = Math.max(size.x, size.y, size.z, 1);
    const distance = reach / (2 * Math.tan((this.camera.fov * Math.PI) / 360)) * 1.5;
    const azimuth = ((this.manifest.camera_azimuth ?? 35) * Math.PI) / 180;
    const elevation = ((this.manifest.camera_elevation ?? 25) * Math.PI) / 180;
    this.camera.position.set(
      Math.cos(elevation) * Math.sin(azimuth) * distance,
      Math.max(Math.sin(elevation) * distance, size.y * 0.3),
      Math.cos(elevation) * Math.cos(azimuth) * distance,
    );
    this.camera.lookAt(0, size.y * 0.4, 0);
    this.distance = distance;
  }

  resize() {
    const width = this.host.clientWidth || 1;
    const height = this.host.clientHeight || Math.round(width * 0.62);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  _tick() {
    if (this.disposed) return;
    this.controls.update(this.clock.getDelta());
    this.renderer.render(this.scene, this.camera);
  }

  setAutoRotate(on) {
    this.controls.autoRotate = on && !prefersReducedMotion();
  }

  reset() {
    const size = new THREE.Box3().setFromObject(this.model).getSize(new THREE.Vector3());
    this._frame(size);
    this.controls.target.set(0, size.y * 0.4, 0);
    this.controls.update();
  }

  /** Re-read the manifest without rebuilding the scene, so a slider is live. */
  reaim(manifest) {
    this.manifest = { ...this.manifest, ...manifest };
    this.setAutoRotate(this.manifest.auto_rotate);
    this.controls.autoRotateSpeed = (this.manifest.rotation_speed ?? 6) / 6;
    this.reset();
  }

  /**
   * A still of exactly what is on screen, for use as the poster.
   *
   * This is why the poster cannot go stale: it is not a render of the model,
   * it is a photograph of the scene the writer is looking at as they save,
   * taken through the same camera the manifest describes.
   */
  capturePoster(maxSide = 640) {
    this.renderer.render(this.scene, this.camera);
    const source = this.renderer.domElement;
    const scale = Math.min(1, maxSide / Math.max(source.width, source.height, 1));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(source.width * scale));
    canvas.height = Math.max(1, Math.round(source.height * scale));
    canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/webp", 0.85));
  }

  // Give the context back. Every one of these matters: without them each
  // reopened viewer leaks a WebGL context until the browser starts dropping
  // the oldest, and the leak shows up as an unrelated figure going blank.
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.renderer.setAnimationLoop(null);
    window.removeEventListener("resize", this._onResize);
    this.controls.dispose();
    this.scene.traverse((node) => {
      if (node.isMesh) {
        node.geometry?.dispose();
        for (const material of [].concat(node.material || [])) {
          for (const value of Object.values(material)) {
            if (value && value.isTexture) value.dispose();
          }
          material.dispose();
        }
      }
    });
    this.ground.geometry.dispose();
    this.ground.material.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

/**
 * Mount a diorama into `host`. Returns a handle the caller disposes.
 *
 * The scene is not built until the host is on screen, and is torn down when the
 * pool needs its context back — so a gallery of twenty dioramas costs four
 * contexts, not twenty.
 */
export function mountDiorama(host, {
  modelUrl, posterUrl, manifest = {}, onError, capture = false, eager = false,
}) {
  const handle = {
    stage: null, sleeping: true, disposed: false,
    sleep: null, wake: null, dispose: null,
  };
  let loading = false;

  const poster = posterUrl ? document.createElement("img") : null;
  if (poster) {
    poster.className = "diorama-poster";
    poster.src = posterUrl;
    poster.alt = "";
    poster.loading = "lazy";
    host.appendChild(poster);
  }

  if (!webglAvailable()) {
    host.classList.add("diorama-static");
    if (!poster && onError) onError(new Error("This browser cannot show 3D scenes."));
    return { dispose() {}, sleep() {}, wake() {}, stage: null };
  }

  async function wake() {
    if (handle.stage || loading || handle.disposed) return;
    loading = true;
    try {
      retireOldest();
      const response = await fetch(modelUrl, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`The model could not be loaded (${response.status}).`);
      const buffer = await response.arrayBuffer();
      if (handle.disposed) return;
      const gltf = await new Promise((resolve, reject) =>
        new GLTFLoader().parse(buffer, "", resolve, reject));
      if (handle.disposed) return;
      // No animation mixer, on purpose: the scene is a moment, not a clip, so
      // any animation the file carries is left unplayed.
      handle.stage = new Stage(host, gltf.scene, manifest, { capture });
      handle.sleeping = false;
      live.add(handle);
      host.classList.add("is-live");
    } catch (error) {
      host.classList.add("diorama-failed");
      if (onError) onError(error);
    } finally {
      loading = false;
    }
  }

  function sleep() {
    live.delete(handle);
    handle.stage?.dispose();
    handle.stage = null;
    handle.sleeping = true;
    host.classList.remove("is-live");
  }

  // The editor preview wants its scene now; an article figure waits until it
  // is nearly on screen, so a long page does not open twenty contexts at once.
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) wake();
    }
  }, { rootMargin: "200px" });
  if (eager) wake();
  else observer.observe(host);

  handle.sleep = sleep;
  handle.wake = wake;
  handle.dispose = () => {
    handle.disposed = true;
    observer.disconnect();
    sleep();
  };
  return handle;
}
