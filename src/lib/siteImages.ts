/** Netlify Image CDN URL for on-demand resize/compress of public assets. */
export function netlifyImageUrl(
  src: string,
  width: number,
  quality = 75,
  format: "webp" | "avif" | "jpg" | "png" = "webp",
): string {
  const params = new URLSearchParams({
    url: src.startsWith("/") ? src : `/${src}`,
    w: String(width),
    q: String(quality),
    fm: format,
  });
  return `/.netlify/images?${params.toString()}`;
}
