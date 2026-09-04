export function HanbitLogo({ className = "" }: { className?: string }) {
  return (
    <img
      className={`hanbit-logo ${className}`.trim()}
      src={`${import.meta.env.BASE_URL}hanbit-logo.png`}
      alt=""
      aria-hidden="true"
      draggable={false}
    />
  );
}
