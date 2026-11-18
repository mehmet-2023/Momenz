/**
 * Hero arka planı: yalnızca ince çizgiler. Küp, zemin/ızgara veya 3D kutu
 * yok. Çizgiler açılışta soldan/sağdan çizilerek gelir, ince bir tarama
 * çizgisi yavaşça aşağı kayar. JS animasyon döngüsü yok.
 */
export default function HeroBackdrop() {
  return (
    <div className="hero-scene" aria-hidden="true">
      <span className="scene-line scene-line-a" />
      <span className="scene-line scene-line-b" />
      <span className="scene-line scene-line-c" />
      <span className="scene-line scene-line-d" />
      <span className="scene-line scene-line-e" />
      <span className="scene-scanline" />
    </div>
  );
}
