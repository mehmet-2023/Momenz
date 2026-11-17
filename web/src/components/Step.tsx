import type { ReactNode } from "react";

type Props = {
  number: string;
  title: string;
  description: string;
  note?: string;
  children: ReactNode;
};

export default function Step({ number, title, description, note, children }: Props) {
  return (
    <section>
      <div className="step-head">
        <div className="step-no">{number}</div>
        <div>
          <div className="step-title">{title}</div>
          <div className="step-desc">{description}</div>
          {note && <div className="step-note">{note}</div>}
        </div>
      </div>
      {children}
    </section>
  );
}
