/**
 * Compresión de fotos en el cliente. Vercel limita el cuerpo de una petición a 4,5 MB y una foto
 * de celular pesa varios MB: se reduce a un máximo de 1600 px y se reencodea a JPEG antes de enviar.
 */

export const MAX_SIDE_PX = 1600;
const QUALITIES = [0.8, 0.65, 0.5];
const MAX_BYTES = 3.5 * 1024 * 1024; // margen bajo el límite de 4,5 MB del cuerpo completo

export class ImageError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ImageError";
  }
}

function toBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

export async function compressImage(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) {
    throw new ImageError("El archivo elegido no es una imagen.");
  }

  let bitmap: ImageBitmap;
  try {
    // "from-image" respeta la orientación EXIF de las fotos tomadas con el celular.
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new ImageError("No se pudo leer la imagen. Prueba con otra foto (JPEG, PNG o WebP).");
  }

  const scale = Math.min(1, MAX_SIDE_PX / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));

  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    throw new ImageError("Tu navegador no pudo procesar la imagen.");
  }
  context.fillStyle = "#ffffff"; // PNG/WebP con transparencia: el JPEG no tiene alfa
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();

  let blob: Blob | null = null;
  for (const quality of QUALITIES) {
    blob = await toBlob(canvas, quality);
    if (blob && blob.size <= MAX_BYTES) break;
  }
  if (!blob || blob.size > MAX_BYTES) {
    throw new ImageError("La foto sigue siendo demasiado pesada. Prueba con otra.");
  }
  return new File([blob], "foto.jpg", { type: "image/jpeg" });
}
