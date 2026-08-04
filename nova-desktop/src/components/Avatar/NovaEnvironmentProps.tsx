import * as THREE from "three";

export function NovaEnvironmentProps() {
  return (
    <group position={[0, -1.95, 0]}>
      {/* Minimal wooden platform */}
      <mesh position={[0, 0, 0]} receiveShadow castShadow>
        <boxGeometry args={[4.8, 0.18, 3.1]} />
        <meshStandardMaterial color="#60422f" roughness={0.74} metalness={0.08} />
      </mesh>

      {/* Small rug */}
      <mesh position={[0, 0.1, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[1.5, 48]} />
        <meshStandardMaterial color="#3e2f2a" roughness={0.92} metalness={0.02} />
      </mesh>

      {/* Sleeping cushion */}
      <mesh position={[0.65, 0.2, 0.35]} castShadow receiveShadow>
        <cylinderGeometry args={[0.56, 0.64, 0.18, 36]} />
        <meshStandardMaterial color="#7b664f" roughness={0.86} metalness={0.03} />
      </mesh>

      {/* Cat bowl */}
      <mesh position={[-1.05, 0.18, 0.45]} castShadow receiveShadow>
        <cylinderGeometry args={[0.16, 0.22, 0.11, 28]} />
        <meshStandardMaterial color="#8e9cb0" roughness={0.35} metalness={0.75} />
      </mesh>

      {/* Small holographic projector */}
      <group position={[1.15, 0.12, -0.42]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[0.3, 0.12, 0.3]} />
          <meshStandardMaterial color="#1e2433" roughness={0.4} metalness={0.4} />
        </mesh>
        <mesh position={[0, 0.08, 0]}>
          <cylinderGeometry args={[0.05, 0.05, 0.02, 20]} />
          <meshStandardMaterial color="#2ed4ff" emissive="#2ed4ff" emissiveIntensity={0.8} roughness={0.1} metalness={0.3} />
        </mesh>
        <mesh position={[0, 0.23, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.09, 0.13, 32]} />
          <meshBasicMaterial color="#66e5ff" transparent opacity={0.35} side={THREE.DoubleSide} />
        </mesh>
      </group>
    </group>
  );
}
