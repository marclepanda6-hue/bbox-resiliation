// Horizontal, transparent Bouygues Telecom logo served by the official website.
const LOGO_SRC = "/bouygues-logo.svg";

export function BrandMark({ size = 56, className = "" }) {
  return (
    <img
      src={LOGO_SRC}
      alt="Bouygues Telecom"
      style={{ height: size, width: "auto" }}
      className={`object-contain ${className}`}
      decoding="async"
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
      decoding="async"
    />
  );
}
