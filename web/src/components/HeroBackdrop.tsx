/**
 * Saf CSS 3D arka plan: iki perspektifli ızgara düzlemi, tell kafes küp ve
 * yatay tarama çizgisi. Fare değişkenleri (--mx / --my) sahnenin açısını
 * hafifçe çevirir; JS animasyon döngüsü yok, GPU bileşimleriyle çalışır.
 */
export default function HeroBackdrop() {
  return (
    <div className="hero-scene" aria-hidden="true">
      <div className="scene-plane scene-plane-a" />
      <div className="scene-plane scene-plane-b" />
      <div className="scene-cube-wrap">
        <div className="scene-cube">
          <span className="cube-face cube-front" />
          <span className="cube-face cube-back" />
          <span className="cube-face cube-right" />
          <span className="cube-face cube-left" />
          <span className="cube-face cube-top" />
          <span className="cube-face cube-bottom" />
        </div>
      </div>
      <div className="scene-scanline" />
    </div>
  );
}
