/**
 * Модалка просмотра фото (свайп, миниатюры, закрытие по подложке).
 * Используется на странице отзывов и на странице товара.
 */
import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useMouseDragHorizontalScroll } from '../../hooks/useMouseDragHorizontalScroll';
import './PhotoGalleryModal.css';

export default function PhotoGalleryModal({ photos, currentIndex: initialIndex = 0, onClose }) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex || 0);
  const trackRef = useRef(null);
  const list = Array.isArray(photos) ? photos : [];
  const total = list.length;
  const safeIndex = total > 0 ? Math.max(0, Math.min(currentIndex, total - 1)) : 0;
  const galleryDragScroll = useMouseDragHorizontalScroll({ disabled: total <= 1 });

  useEffect(() => {
    if (total <= 1 || !trackRef.current) return;
    const el = trackRef.current;
    const w = el.clientWidth;
    el.scrollTo({ left: safeIndex * w, behavior: 'smooth' });
  }, [safeIndex, total]);

  const handleTrackScroll = useCallback(() => {
    const el = trackRef.current;
    if (!el || total <= 1) return;
    const w = el.clientWidth;
    const idx = Math.round(el.scrollLeft / w);
    setCurrentIndex(Math.max(0, Math.min(idx, total - 1)));
  }, [total]);

  const getImageSrc = (path) => {
    if (typeof path === 'string') return path.startsWith('http') ? path : `/${path}`;
    if (path && typeof path === 'object' && path.file_path) return `/${path.file_path}`;
    return '';
  };

  const srcList = list.map((p) => getImageSrc(p));

  return (
    <div
      className="photo-gallery-modal__backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Фотографии"
    >
      <div className="photo-gallery-modal__modal" onClick={(e) => e.stopPropagation()}>
        <div className="photo-gallery-modal__body">
          <div className="photo-gallery-modal__frame">
            {total > 0 ? (
              <div
                ref={trackRef}
                className={`photo-gallery-modal__track ${total === 1 ? 'photo-gallery-modal__track--single' : ''}`}
                onScroll={handleTrackScroll}
                {...galleryDragScroll.dragScrollProps}
              >
                {srcList.map((src, idx) => (
                  <div
                    key={idx}
                    className={`photo-gallery-modal__slide ${total === 1 ? 'photo-gallery-modal__slide--single' : ''}`}
                  >
                    <img src={src} alt="" className="photo-gallery-modal__img" />
                  </div>
                ))}
              </div>
            ) : (
              <span className="photo-gallery-modal__empty">Нет фото</span>
            )}
          </div>
          {total > 1 && (
            <div className="photo-gallery-modal__thumbs">
                {srcList.map((src, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className={`photo-gallery-modal__thumb ${idx === safeIndex ? 'photo-gallery-modal__thumb--current' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setCurrentIndex(idx);
                    }}
                    aria-label={`Фото ${idx + 1}`}
                  >
                    <img src={src} alt="" />
                  </button>
                ))}
              </div>
          )}
        </div>
      </div>
    </div>
  );
}
