/**
 * Центральный квадратный кроп и ресайз до outSize (JPEG). EXIF через createImageBitmap.
 * @param {File} file
 * @param {number} [outSize=384]
 * @param {number} [quality=0.88]
 * @returns {Promise<Blob>}
 */
export async function fileToSquareAvatarJpeg(file, outSize = 384, quality = 0.88) {
  if (!file || !/^image\//.test(file.type)) {
    throw new Error('not_image');
  }
  let bmp;
  try {
    bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    try {
      bmp = await createImageBitmap(file);
    } catch {
      throw new Error('decode_failed');
    }
  }
  try {
    const w = bmp.width;
    const h = bmp.height;
    const side = Math.min(w, h);
    const sx = (w - side) / 2;
    const sy = (h - side) / 2;
    const canvas = document.createElement('canvas');
    canvas.width = outSize;
    canvas.height = outSize;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('no_ctx');
    ctx.drawImage(bmp, sx, sy, side, side, 0, 0, outSize, outSize);
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('toBlob'))), 'image/jpeg', quality);
    });
    return blob;
  } finally {
    try {
      bmp.close();
    } catch {
      /* ignore */
    }
  }
}
