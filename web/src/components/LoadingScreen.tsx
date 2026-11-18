import HeroBackdrop from "@/components/HeroBackdrop";

type Props = {
  label?: string;
  variant?: "detail" | "form";
};

export default function LoadingScreen({
  label = "YÜKLENİYOR",
  variant = "detail",
}: Props) {
  return (
    <div className={`load-screen load-screen-${variant}`} role="status" aria-live="polite">
      <HeroBackdrop />
      <div className="load-content">
        <div className="load-top">
          <div className="load-mark">◼</div>
          <div className="load-heading">
            <div className="eyebrow">MOMENZ / SİSTEM</div>
            <div className="load-title">{label}</div>
          </div>
          <div className="load-counter">···</div>
        </div>
        <div className="load-bar"><span /></div>
        <div className="load-grid">
          {Array.from({ length: variant === "detail" ? 8 : 4 }, (_, i) => (
            <div className="load-cell skeleton" key={i} />
          ))}
        </div>
        <div className="load-foot">
          <span>BEKLEME SÜRESİ INDEX DURUMUNA BAĞLI</span>
          <span>ESC İLE İPTAL EDİLEMEZ</span>
        </div>
      </div>
    </div>
  );
}
