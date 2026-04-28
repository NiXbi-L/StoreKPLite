/**
 * Сжимает изображение для загрузки: ресайз по большей стороне и JPEG качество.
 * @param {File} file
 * @param {{ maxSize?: number, quality?: number }} [opts] — maxSize по большей стороне (по умолчанию 1200), quality 0–1 (по умолчанию 0.82)
 * @returns {Promise<Blob>}
 */
export function compressImage(file, opts = {}) {
  const maxSize = opts.maxSize ?? 1200;
  const quality = opts.quality ?? 0.82;

  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Не удалось загрузить изображение'));
    };
    img.onload = () => {
      URL.revokeObjectURL(url);
      let { width, height } = img;
      if (width > maxSize || height > maxSize) {
        if (width >= height) {
          height = Math.round((height * maxSize) / width);
          width = maxSize;
        } else {
          width = Math.round((width * maxSize) / height);
          height = maxSize;
        }
      }
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        reject(new Error('Canvas не поддерживается'));
        return;
      }
      ctx.drawImage(img, 0, 0, width, height);
      canvas.toBlob(
        (blob) => {
          if (blob) resolve(blob);
          else reject(new Error('Не удалось сжать изображение'));
        },
        'image/jpeg',
        quality
      );
    };
    img.src = url;
  });
}
