/**
 * Перед загрузкой на бэкенд «вшиваем» EXIF Orientation в пиксели.
 * Иначе в Telegram WebView / части браузеров на сервер уходит JPEG с тегом Orientation,
 * а декодер на бэке видит сырые w/h — кроп 9:16 ломается (поворот / полосы).
 */
export async function normalizeImageFileForUpload(file) {
  if (!file || !/^image\//.test(file.type)) return file;

  let bmp;
  try {
    bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    try {
      bmp = await createImageBitmap(file);
    } catch {
      return file;
    }
  }

  try {
    const maxSide = 2048;
    let w = bmp.width;
    let h = bmp.height;
    if (w > maxSide || h > maxSide) {
      const k = maxSide / Math.max(w, h);
      w = Math.max(1, Math.round(w * k));
      h = Math.max(1, Math.round(h * k));
    }

    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;
    ctx.drawImage(bmp, 0, 0, w, h);

    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('toBlob'))), 'image/jpeg', 0.92);
    });
    const base = (file.name && file.name.replace(/\.[^.]+$/, '')) || 'photo';
    return new File([blob], `${base}.jpg`, { type: 'image/jpeg' });
  } catch {
    return file;
  } finally {
    try {
      bmp.close();
    } catch {
      /* ignore */
    }
  }
}
