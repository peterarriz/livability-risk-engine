import type { ComponentPropsWithoutRef, ReactNode } from "react";

type ContainerProps = {
  children: ReactNode;
  className?: string;
};

type SectionProps = Omit<ComponentPropsWithoutRef<"section">, "children"> & {
  children: ReactNode;
  eyebrow?: string;
  title?: string;
  description?: string;
  headerAction?: ReactNode;
};

type CardProps = ContainerProps & {
  tone?: "default" | "highlighted";
};

function joinClasses(...classes: Array<string | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function Container({ children, className }: ContainerProps) {
  return <div className={joinClasses("shell-container", className)}>{children}</div>;
}

export function Header({ children, className }: ContainerProps) {
  return <header className={joinClasses("shell-header", className)}>{children}</header>;
}

export function Section({
  children,
  eyebrow,
  title,
  description,
  headerAction,
  className,
  ...sectionProps
}: SectionProps) {
  return (
    <section className={joinClasses("shell-section", className)} {...sectionProps}>
      {eyebrow || title || description || headerAction ? (
        <div className={joinClasses("section-heading", headerAction ? "section-heading--with-action" : undefined)}>
          <div>
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            {title ? <h2>{title}</h2> : null}
            {description ? <p className="section-copy">{description}</p> : null}
          </div>
          {headerAction ? <div className="section-header-action">{headerAction}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Card({ children, className, tone = "default" }: CardProps) {
  return (
    <div className={joinClasses("surface-card", tone === "highlighted" ? "surface-card--hero" : undefined, className)}>
      {children}
    </div>
  );
}
