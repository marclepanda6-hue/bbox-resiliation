// Bouygues Telecom brand logo (image provided by the client).
const LOGO_SRC = "/bouygues-logo.jpg";

export function BrandMark({ size = 56, className = "" }) {
  return (
    <img
      src={LOGO_SRC}
      alt="Bouygues Telecom"
      style={{ height: size, width: "auto" }}
      className={`object-contain ${className}`}
    />
  );
}

export function BrandLogo({ markSize = 52, className = "" }) {
  return (
    <img
      src={LOGO_SRC}
      alt="Bouygues Telecom"
      style={{ height: Math.round(markSize * 0.92), width: "auto" }}
      className={`object-contain ${className}`}
    />
  );
}
