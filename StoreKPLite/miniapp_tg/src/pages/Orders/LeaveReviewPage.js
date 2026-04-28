import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { getOrder, createOrderReview } from '../../api/products';
import { compressImage } from '../../utils/compressImage';
import Button from '../../components/Button';
import './LeaveReviewPage.css';

const MAX_PHOTOS = 10;
const STAR_FILL = '#171717';

function StarRatingInput({ value, onChange, className }) {
  return (
    <div className={`leave-review__stars ${className || ''}`} role="group" aria-label="Оценка">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          className="leave-review__star-btn"
          onClick={() => onChange(n)}
          aria-label={`${n} из 5`}
          aria-pressed={value === n}
        >
          <svg width="32" height="32" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M14.9488 6.07866C14.8863 5.88649 14.7683 5.71712 14.6097 5.59188C14.4511 5.46665 14.259 5.39116 14.0575 5.37491L10.37 5.07741L8.94629 1.63429C8.8693 1.44667 8.73825 1.28619 8.56981 1.17325C8.40137 1.06031 8.20315 1 8.00035 1C7.79756 1 7.59934 1.06031 7.4309 1.17325C7.26246 1.28619 7.13141 1.44667 7.05442 1.63429L5.63192 5.07679L1.94254 5.37491C1.74078 5.39198 1.54854 5.4682 1.3899 5.59404C1.23127 5.71988 1.1133 5.88973 1.05077 6.08232C0.988239 6.27491 0.983936 6.48167 1.0384 6.67669C1.09286 6.87172 1.20366 7.04633 1.35692 7.17866L4.16942 9.60554L3.31254 13.2343C3.26462 13.4314 3.27635 13.6384 3.34625 13.8288C3.41615 14.0193 3.54107 14.1847 3.70514 14.304C3.86921 14.4234 4.06505 14.4913 4.26778 14.4991C4.47051 14.5069 4.671 14.4544 4.84379 14.348L8.00004 12.4055L11.1582 14.348C11.331 14.4531 11.5311 14.5047 11.7332 14.4962C11.9353 14.4878 12.1304 14.4198 12.2939 14.3007C12.4574 14.1816 12.5821 14.0168 12.6521 13.8271C12.7221 13.6373 12.7345 13.431 12.6875 13.2343L11.8275 9.60491L14.64 7.17804C14.7945 7.04593 14.9064 6.87094 14.9613 6.67522C15.0163 6.47951 15.0119 6.27189 14.9488 6.07866Z"
              fill={value >= n ? STAR_FILL : 'none'}
              stroke={STAR_FILL}
              strokeWidth="0.5"
            />
          </svg>
        </button>
      ))}
    </div>
  );
}

export default function LeaveReviewPage() {
  const { orderId } = useParams();
  const [searchParams] = useSearchParams();
  const preselectedItemId = searchParams.get('itemId') ? Number(searchParams.get('itemId')) : null;
  const navigate = useNavigate();
  const { setTabBarVisible } = useTabBarVisibility();

  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [itemsForReview, setItemsForReview] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [photoFiles, setPhotoFiles] = useState([]);
  const [previewUrls, setPreviewUrls] = useState([]);
  const previewUrlsRef = useRef([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    setTabBarVisible(false);
    const tg = window.Telegram?.WebApp;
    const backButton = tg?.BackButton;
    if (!backButton) return () => setTabBarVisible(true);
    const handleBack = () => navigate(-1);
    backButton.onClick(handleBack);
    backButton.show();
    return () => {
      backButton.offClick(handleBack);
      backButton.hide();
      setTabBarVisible(true);
    };
  }, [navigate, setTabBarVisible]);

  useEffect(() => {
    if (!orderId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getOrder(Number(orderId))
      .then((data) => {
        if (cancelled) return;
        setOrder(data);
        if (data.status !== 'завершен') {
          navigate('/main/profile/orders', { replace: true });
          return;
        }
        const items = (data.order_data?.items || []).filter((row) => !row.returned && row.item_id != null);
        const byItem = new Map();
        items.forEach((row) => {
          if (!byItem.has(row.item_id)) byItem.set(row.item_id, row);
        });
        let list = Array.from(byItem.values());
        if (Array.isArray(data.reviewable_item_ids) && data.reviewable_item_ids.length >= 0) {
          list = list.filter((row) => data.reviewable_item_ids.includes(row.item_id));
        }
        setItemsForReview(list);
        if (list.length === 1) {
          setSelectedItem(list[0]);
        } else if (preselectedItemId && list.some((r) => r.item_id === preselectedItemId)) {
          setSelectedItem(list.find((r) => r.item_id === preselectedItemId));
        } else {
          setSelectedItem(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e.message || 'Не удалось загрузить заказ');
          setOrder(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [orderId, preselectedItemId, navigate]);

  const handlePhotoChange = useCallback((e) => {
    const files = Array.from(e.target.files || []);
    setPhotoFiles((prev) => {
      const next = [...prev];
      for (const f of files) {
        if (!f.type.startsWith('image/')) continue;
        if (next.length >= MAX_PHOTOS) break;
        next.push(f);
      }
      return next.slice(0, MAX_PHOTOS);
    });
    e.target.value = '';
  }, []);

  useEffect(() => {
    previewUrlsRef.current.forEach((u) => URL.revokeObjectURL(u));
    const urls = photoFiles.map((f) => URL.createObjectURL(f));
    previewUrlsRef.current = urls;
    setPreviewUrls(urls);
    return () => {
      urls.forEach((u) => URL.revokeObjectURL(u));
      previewUrlsRef.current = [];
    };
  }, [photoFiles]);

  const removePhoto = useCallback((index) => {
    setPhotoFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!orderId || !selectedItem) return;
    if (rating < 1 || rating > 5) {
      setSubmitError('Выберите оценку от 1 до 5');
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const blobs = [];
      for (const file of photoFiles) {
        try {
          const blob = await compressImage(file);
          blobs.push(blob);
        } catch (err) {
          console.warn('Compress skip', file.name, err);
        }
      }
      // Показываем «отзыв отправлен» сразу, запрос уходит в фоне без ожидания ответа
      setSuccess(true);
      setSubmitting(false);
      createOrderReview(Number(orderId), {
        item_id: selectedItem.item_id,
        rating,
        comment: comment.trim(),
        photoBlobs: blobs,
      }).catch((e) => {
        console.warn('Отправка отзыва в фоне не удалась:', e);
      });
      setTimeout(() => {
        navigate('/main/profile/orders', { replace: true });
      }, 1500);
    } catch (e) {
      setSubmitError(e.message || 'Не удалось подготовить отзыв');
      setSubmitting(false);
    }
  }, [orderId, selectedItem, rating, comment, photoFiles, navigate]);

  if (loading) {
    return (
      <div className="leave-review page-container">
        <div className="leave-review__header">Оставить отзыв</div>
        <p className="leave-review__status">Загрузка…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="leave-review page-container">
        <div className="leave-review__header">Оставить отзыв</div>
        <p className="leave-review__status leave-review__status--error" role="alert">{error}</p>
        <Button variant="secondary" onClick={() => navigate('/main/profile/orders')}>К заказам</Button>
      </div>
    );
  }

  if (!order || itemsForReview.length === 0) {
    return (
      <div className="leave-review page-container">
        <div className="leave-review__header">Оставить отзыв</div>
        <p className="leave-review__status">В заказе нет товаров для отзыва.</p>
        <Button variant="secondary" onClick={() => navigate('/main/profile/orders')}>К заказам</Button>
      </div>
    );
  }

  if (!selectedItem) {
    return (
      <div className="leave-review page-container">
        <div className="leave-review__header">Выберите товар для отзыва</div>
        <ul className="leave-review__item-list">
          {itemsForReview.map((row) => {
            const photoPath = row.photo ? `/${row.photo}` : null;
            return (
              <li key={row.item_id} className="leave-review__item-row">
                <button
                  type="button"
                  className="leave-review__item-btn"
                  onClick={() => setSelectedItem(row)}
                >
                  {photoPath ? (
                    <img src={photoPath} alt="" className="leave-review__item-photo" />
                  ) : (
                    <span className="leave-review__item-photo-placeholder" />
                  )}
                  <span className="leave-review__item-name">{row.name || 'Товар'}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  if (success) {
    return (
      <div className="leave-review page-container">
        <div className="leave-review__header">Спасибо!</div>
        <p className="leave-review__status">Ваш отзыв отправлен.</p>
      </div>
    );
  }

  return (
    <div className="leave-review page-container">
      <div className="leave-review__header">Оставить отзыв</div>
      <div className="leave-review__product">
        {selectedItem.photo ? (
          <img src={`/${selectedItem.photo}`} alt="" className="leave-review__product-img" />
        ) : (
          <span className="leave-review__product-img-placeholder" />
        )}
        <span className="leave-review__product-name">{selectedItem.name || 'Товар'}</span>
      </div>

      <div className="leave-review__field">
        <label className="leave-review__label">Оценка</label>
        <StarRatingInput value={rating} onChange={setRating} />
      </div>

      <div className="leave-review__field">
        <label className="leave-review__label" htmlFor="leave-review-comment">Комментарий (необязательно)</label>
        <textarea
          id="leave-review-comment"
          className="leave-review__textarea"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Расскажите о товаре"
          rows={4}
          maxLength={2000}
        />
      </div>

      <div className="leave-review__field">
        <label className="leave-review__label">Фото (до {MAX_PHOTOS})</label>
        <input
          type="file"
          accept="image/*"
          multiple
          className="leave-review__file-input"
          onChange={handlePhotoChange}
          disabled={photoFiles.length >= MAX_PHOTOS}
        />
        {previewUrls.length > 0 && (
          <div className="leave-review__previews">
            {previewUrls.map((url, idx) => (
              <div key={idx} className="leave-review__preview-wrap">
                <img src={url} alt="" className="leave-review__preview-img" />
                <button
                  type="button"
                  className="leave-review__preview-remove"
                  onClick={() => removePhoto(idx)}
                  aria-label="Удалить фото"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {submitError && (
        <p className="leave-review__submit-error" role="alert">{submitError}</p>
      )}

      <Button
        type="button"
        size="large"
        variant="primary"
        className="leave-review__submit"
        loading={submitting}
        disabled={submitting}
        onClick={handleSubmit}
      >
        {submitting ? 'Отправка…' : 'Отправить отзыв'}
      </Button>
    </div>
  );
}
