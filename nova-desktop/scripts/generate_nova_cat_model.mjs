import fs from "node:fs/promises";
import path from "node:path";
import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";

function installNodeFileReaderPolyfill() {
  if (typeof globalThis.FileReader !== "undefined") {
    return;
  }

  class NodeFileReader {
    constructor() {
      this.result = null;
      this.error = null;
      this.onload = null;
      this.onerror = null;
      this.onloadend = null;
    }

    async readAsArrayBuffer(blob) {
      try {
        this.result = await blob.arrayBuffer();
        if (this.onload) this.onload({ target: this });
      } catch (err) {
        this.error = err;
        if (this.onerror) this.onerror(err);
      } finally {
        if (this.onloadend) this.onloadend({ target: this });
      }
    }

    async readAsDataURL(blob) {
      try {
        const buffer = Buffer.from(await blob.arrayBuffer());
        const mime = blob.type || "application/octet-stream";
        this.result = `data:${mime};base64,${buffer.toString("base64")}`;
        if (this.onload) this.onload({ target: this });
      } catch (err) {
        this.error = err;
        if (this.onerror) this.onerror(err);
      } finally {
        if (this.onloadend) this.onloadend({ target: this });
      }
    }
  }

  globalThis.FileReader = NodeFileReader;
}

function makeMaterial(color, roughness = 0.72, metalness = 0.06) {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness });
}

function buildNovaCat() {
  const root = new THREE.Group();
  root.name = "NOVA_Cat_Root";

  const cat = new THREE.Group();
  cat.name = "NOVA_Cat_Main";
  root.add(cat);

  const furMain = makeMaterial("#c98643", 0.82, 0.02);
  const furCream = makeMaterial("#e8d8ba", 0.9, 0.01);
  const furWhite = makeMaterial("#f3efe6", 0.88, 0.01);
  const noseMat = makeMaterial("#d88fa2", 0.6, 0.03);
  const eyeGreen = makeMaterial("#6aa94a", 0.28, 0.05);
  const pupilMat = makeMaterial("#111111", 0.22, 0.12);
  const collarMat = makeMaterial("#152033", 0.65, 0.22);
  const tagMat = makeMaterial("#9ea5b1", 0.35, 0.82);
  const cyanGlow = new THREE.MeshStandardMaterial({
    color: "#38dfff",
    emissive: "#38dfff",
    emissiveIntensity: 0.65,
    roughness: 0.25,
    metalness: 0.12,
  });

  const torso = new THREE.Mesh(new THREE.SphereGeometry(0.62, 48, 32), furMain);
  torso.name = "Torso";
  torso.scale.set(1.0, 0.84, 1.25);
  torso.position.set(0, 0.04, 0);
  cat.add(torso);

  const chest = new THREE.Mesh(new THREE.SphereGeometry(0.42, 38, 28), furWhite);
  chest.name = "Chest";
  chest.scale.set(0.88, 0.94, 0.82);
  chest.position.set(0, -0.02, 0.43);
  cat.add(chest);

  const headGroup = new THREE.Group();
  headGroup.name = "Head";
  headGroup.position.set(0, 0.58, 0.34);
  cat.add(headGroup);

  const head = new THREE.Mesh(new THREE.SphereGeometry(0.34, 48, 36), furMain);
  head.name = "Head_Mesh";
  head.scale.set(1.05, 0.95, 1.0);
  headGroup.add(head);

  const muzzle = new THREE.Mesh(new THREE.SphereGeometry(0.18, 32, 24), furCream);
  muzzle.name = "Muzzle";
  muzzle.scale.set(1.25, 0.72, 0.92);
  muzzle.position.set(0, -0.08, 0.27);
  headGroup.add(muzzle);

  const nose = new THREE.Mesh(new THREE.SphereGeometry(0.04, 16, 12), noseMat);
  nose.name = "Nose";
  nose.scale.set(1.3, 0.95, 0.9);
  nose.position.set(0, -0.08, 0.41);
  headGroup.add(nose);

  const leftEye = new THREE.Mesh(new THREE.SphereGeometry(0.065, 20, 14), eyeGreen);
  leftEye.name = "Eye_L";
  leftEye.scale.set(1.0, 0.92, 0.62);
  leftEye.position.set(-0.12, 0.02, 0.29);
  headGroup.add(leftEye);

  const rightEye = leftEye.clone();
  rightEye.name = "Eye_R";
  rightEye.position.x = 0.12;
  headGroup.add(rightEye);

  const pupilL = new THREE.Mesh(new THREE.SphereGeometry(0.018, 14, 10), pupilMat);
  pupilL.name = "Pupil_L";
  pupilL.scale.set(0.8, 1.7, 0.8);
  pupilL.position.set(-0.12, 0.02, 0.335);
  headGroup.add(pupilL);

  const pupilR = pupilL.clone();
  pupilR.name = "Pupil_R";
  pupilR.position.x = 0.12;
  headGroup.add(pupilR);

  const earL = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.2, 4), furMain);
  earL.name = "Ear_L";
  earL.rotation.set(0.2, 0.15, -0.18);
  earL.position.set(-0.18, 0.23, 0.03);
  headGroup.add(earL);

  const earR = earL.clone();
  earR.name = "Ear_R";
  earR.rotation.z = 0.18;
  earR.position.x = 0.18;
  headGroup.add(earR);

  const legPositions = [
    [-0.24, -0.54, 0.3],
    [0.24, -0.54, 0.3],
    [-0.24, -0.54, -0.26],
    [0.24, -0.54, -0.26],
  ];

  legPositions.forEach((p, i) => {
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.095, 0.44, 8, 18), furMain);
    leg.name = `Leg_${i + 1}`;
    leg.position.set(p[0], p[1], p[2]);
    cat.add(leg);

    const paw = new THREE.Mesh(new THREE.SphereGeometry(0.11, 18, 14), furWhite);
    paw.name = `Paw_${i + 1}`;
    paw.scale.set(1.08, 0.7, 1.2);
    paw.position.set(p[0], p[1] - 0.3, p[2] + 0.02);
    cat.add(paw);
  });

  const tailRoot = new THREE.Group();
  tailRoot.name = "Tail_Root";
  tailRoot.position.set(0, -0.03, -0.58);
  cat.add(tailRoot);

  const tail1 = new THREE.Mesh(new THREE.CapsuleGeometry(0.09, 0.28, 8, 16), furMain);
  tail1.name = "Tail_01";
  tail1.rotation.set(0.95, 0, 0.18);
  tailRoot.add(tail1);

  const tail2 = new THREE.Mesh(new THREE.CapsuleGeometry(0.075, 0.25, 8, 14), furMain);
  tail2.name = "Tail_02";
  tail2.position.set(0, 0.18, -0.06);
  tail2.rotation.set(0.68, 0, -0.2);
  tail1.add(tail2);

  const tail3 = new THREE.Mesh(new THREE.CapsuleGeometry(0.062, 0.22, 8, 14), furMain);
  tail3.name = "Tail_03";
  tail3.position.set(0, 0.16, -0.03);
  tail3.rotation.set(0.52, 0, 0.12);
  tail2.add(tail3);

  const collar = new THREE.Mesh(new THREE.TorusGeometry(0.29, 0.028, 18, 56), collarMat);
  collar.name = "Collar";
  collar.rotation.x = Math.PI / 2;
  collar.position.set(0, 0.44, 0.23);
  cat.add(collar);

  const pendant = new THREE.Mesh(new THREE.SphereGeometry(0.04, 20, 16), cyanGlow);
  pendant.name = "Pendant";
  pendant.position.set(0, 0.28, 0.49);
  cat.add(pendant);

  const tag = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.055, 0.012), tagMat);
  tag.name = "Tag_NOVA";
  tag.position.set(0.08, 0.3, 0.48);
  cat.add(tag);

  return { root, nodes: { root, cat, headGroup, tailRoot, tail1, tail2, tail3, earL, earR } };
}

function buildAnimationClips(nodes) {
  const clips = [];

  const idleTrack = new THREE.VectorKeyframeTrack(
    "NOVA_Cat_Main.position",
    [0, 1.4, 2.8],
    [0, 0, 0, 0, 0.018, 0, 0, 0, 0]
  );
  clips.push(new THREE.AnimationClip("NOVA_Idle_01", 2.8, [idleTrack]));

  const idle2 = new THREE.QuaternionKeyframeTrack(
    "Head.quaternion",
    [0, 1.2, 2.4],
    [0, 0, 0, 1, 0, 0.07, 0, 0.9975, 0, -0.05, 0, 0.9987]
  );
  clips.push(new THREE.AnimationClip("NOVA_Idle_02", 2.4, [idle2]));

  clips.push(new THREE.AnimationClip("NOVA_Idle_03", 2.2, [
    new THREE.VectorKeyframeTrack("NOVA_Cat_Main.scale", [0, 1.1, 2.2], [1, 1, 1, 1.01, 0.99, 1.01, 1, 1, 1]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Idle_04", 2.4, [
    new THREE.VectorKeyframeTrack("Tail_Root.position", [0, 1.2, 2.4], [0, -0.03, -0.58, -0.02, -0.03, -0.58, 0, -0.03, -0.58]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Blink", 0.35, [
    new THREE.VectorKeyframeTrack("Eye_L.scale", [0, 0.16, 0.35], [1, 0.92, 0.62, 1, 0.12, 0.62, 1, 0.92, 0.62]),
    new THREE.VectorKeyframeTrack("Eye_R.scale", [0, 0.16, 0.35], [1, 0.92, 0.62, 1, 0.12, 0.62, 1, 0.92, 0.62]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Ear_Twitch", 0.8, [
    new THREE.VectorKeyframeTrack("Ear_L.scale", [0, 0.35, 0.8], [1, 1, 1, 1.04, 1.12, 1.04, 1, 1, 1]),
    new THREE.VectorKeyframeTrack("Ear_R.scale", [0, 0.35, 0.8], [1, 1, 1, 1.04, 1.12, 1.04, 1, 1, 1]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Tail_Movement", 1.8, [
    new THREE.VectorKeyframeTrack("Tail_02.position", [0, 0.9, 1.8], [0, 0.18, -0.06, -0.05, 0.2, -0.06, 0, 0.18, -0.06]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Listen", 1.2, [
    new THREE.VectorKeyframeTrack("Head.position", [0, 0.6, 1.2], [0, 0.58, 0.34, -0.04, 0.58, 0.34, 0.04, 0.58, 0.34]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Thinking", 1.5, [
    new THREE.VectorKeyframeTrack("Head.position", [0, 0.75, 1.5], [0, 0.58, 0.34, 0, 0.61, 0.35, 0, 0.58, 0.34]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Talking", 0.55, [
    new THREE.VectorKeyframeTrack("Muzzle.scale", [0, 0.27, 0.55], [1.25, 0.72, 0.92, 1.28, 0.82, 0.92, 1.25, 0.72, 0.92]),
    new THREE.VectorKeyframeTrack("NOVA_Cat_Main.position", [0, 0.27, 0.55], [0, 0, 0, 0, 0.03, 0, 0, 0, 0]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Sleep", 2.2, [
    new THREE.VectorKeyframeTrack("Head.position", [0, 1.1, 2.2], [0, 0.58, 0.34, 0, 0.46, 0.38, 0, 0.46, 0.38]),
    new THREE.VectorKeyframeTrack("NOVA_Cat_Main.scale", [0, 1.1, 2.2], [1, 1, 1, 1.02, 0.96, 1.02, 1, 1, 1]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Observe_User", 1.6, [
    new THREE.VectorKeyframeTrack("Head.position", [0, 0.8, 1.6], [0, 0.58, 0.34, -0.03, 0.58, 0.34, 0.03, 0.58, 0.34]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Look_Around", 1.4, [
    new THREE.VectorKeyframeTrack("Head.position", [0, 0.7, 1.4], [0, 0.58, 0.34, 0.06, 0.58, 0.34, -0.06, 0.58, 0.34]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Celebrate", 0.9, [
    new THREE.VectorKeyframeTrack("NOVA_Cat_Main.position", [0, 0.45, 0.9], [0, 0, 0, 0, 0.14, 0, 0, 0, 0]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Happy_Jump", 1.0, [
    new THREE.VectorKeyframeTrack("NOVA_Cat_Main.position", [0, 0.5, 1.0], [0, 0, 0, 0, 0.22, 0, 0, 0, 0]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Concerned", 1.1, [
    new THREE.VectorKeyframeTrack("Head.position", [0, 0.55, 1.1], [0, 0.58, 0.34, 0, 0.54, 0.34, 0, 0.58, 0.34]),
  ]));

  clips.push(new THREE.AnimationClip("NOVA_Tail_Wag", 1.0, [
    new THREE.VectorKeyframeTrack("Tail_03.position", [0, 0.5, 1.0], [0, 0.16, -0.03, 0.05, 0.17, -0.03, 0, 0.16, -0.03]),
  ]));

  // Alias clips required by runtime spec but represented by reusing similar motion.
  const alias = (name, source) => {
    const src = clips.find((c) => c.name === source);
    if (src) clips.push(new THREE.AnimationClip(name, src.duration, src.tracks));
  };

  alias("NOVA_Stretch", "NOVA_Idle_03");
  alias("NOVA_Yawn", "NOVA_Talking");
  alias("NOVA_Walk", "NOVA_Look_Around");
  alias("NOVA_Run", "NOVA_Celebrate");
  alias("NOVA_Sit", "NOVA_Idle_01");
  alias("NOVA_Lie_Down", "NOVA_Sleep");
  alias("NOVA_Wake_Up", "NOVA_Idle_02");
  alias("NOVA_Eat", "NOVA_Talking");
  alias("NOVA_Drink", "NOVA_Talking");
  alias("NOVA_Confused", "NOVA_Thinking");
  alias("NOVA_Scratch_Ear", "NOVA_Ear_Twitch");
  alias("NOVA_Clean_Paw", "NOVA_Idle_04");

  return clips;
}

async function exportGLB(scene, animations, targetPath) {
  installNodeFileReaderPolyfill();
  const exporter = new GLTFExporter();
  const glb = await new Promise((resolve, reject) => {
    exporter.parse(
      scene,
      (result) => resolve(result),
      (error) => reject(error),
      {
        binary: true,
        trs: false,
        onlyVisible: false,
        maxTextureSize: 4096,
        animations,
        includeCustomExtensions: false,
      }
    );
  });

  const buf = Buffer.from(glb);
  await fs.mkdir(path.dirname(targetPath), { recursive: true });
  await fs.writeFile(targetPath, buf);
  return buf.length;
}

async function main() {
  const { root, nodes } = buildNovaCat();
  const clips = buildAnimationClips(nodes);

  const targetPath = path.resolve(
    process.cwd(),
    "public/models/persian_cat.glb"
  );

  const bytes = await exportGLB(root, clips, targetPath);

  console.log(`Generated: ${targetPath}`);
  console.log(`Size: ${(bytes / 1024).toFixed(1)} KB`);
  console.log(`Clips: ${clips.length}`);
  console.log(`Model: NOVA light-orange Persian companion`);
}

main().catch((err) => {
  console.error("Failed to generate model", err);
  process.exit(1);
});
