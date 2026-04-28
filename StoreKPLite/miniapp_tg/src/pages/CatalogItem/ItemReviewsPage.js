/**
 * Отдельная страница отзывов по товару (как на скринах: заголовок, фильтр, средняя оценка, список, модалка фото).
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { getItemReviewsSummary, getItemReviews } from '../../api/products';
import AvatarWithFallback from '../../components/AvatarWithFallback';
import PhotoGalleryModal from '../../components/PhotoGalleryModal';
import './ItemReviewsPage.css';

const STAR_FILL = '#171717';

function StarRating({ rating, className }) {
  const r = Math.min(5, Math.max(0, Number(rating) || 0));
  const full = Math.floor(r);
  const half = r - full >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  const stars = [];
  for (let i = 0; i < full; i++) stars.push('full');
  for (let i = 0; i < half; i++) stars.push('half');
  for (let i = 0; i < empty; i++) stars.push('empty');
  return (
    <span className={className} role="img" aria-label={`Оценка ${r} из 5`}>
      {stars.map((t, idx) => (
        <span key={idx} className="reviews-page__star-wrap">
          {t === 'full' && (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M14.9488 6.07866C14.8863 5.88649 14.7683 5.71712 14.6097 5.59188C14.4511 5.46665 14.259 5.39116 14.0575 5.37491L10.37 5.07741L8.94629 1.63429C8.8693 1.44667 8.73825 1.28619 8.56981 1.17325C8.40137 1.06031 8.20315 1 8.00035 1C7.79756 1 7.59934 1.06031 7.4309 1.17325C7.26246 1.28619 7.13141 1.44667 7.05442 1.63429L5.63192 5.07679L1.94254 5.37491C1.74078 5.39198 1.54854 5.4682 1.3899 5.59404C1.23127 5.71988 1.1133 5.88973 1.05077 6.08232C0.988239 6.27491 0.983936 6.48167 1.0384 6.67669C1.09286 6.87172 1.20366 7.04633 1.35692 7.17866L4.16942 9.60554L3.31254 13.2343C3.26462 13.4314 3.27635 13.6384 3.34625 13.8288C3.41615 14.0193 3.54107 14.1847 3.70514 14.304C3.86921 14.4234 4.06505 14.4913 4.26778 14.4991C4.47051 14.5069 4.671 14.4544 4.84379 14.348L8.00004 12.4055L11.1582 14.348C11.331 14.4531 11.5311 14.5047 11.7332 14.4962C11.9353 14.4878 12.1304 14.4198 12.2939 14.3007C12.4574 14.1816 12.5821 14.0168 12.6521 13.8271C12.7221 13.6373 12.7345 13.431 12.6875 13.2343L11.8275 9.60491L14.64 7.17804C14.7945 7.04593 14.9064 6.87094 14.9613 6.67522C15.0163 6.47951 15.0119 6.27189 14.9488 6.07866Z" fill={STAR_FILL} />
            </svg>
          )}
          {t === 'half' && (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M14.9488 6.07866C14.8863 5.88649 14.7683 5.71712 14.6097 5.59188C14.4511 5.46665 14.259 5.39116 14.0575 5.37491L10.37 5.07741L8.94629 1.63429C8.8693 1.44667 8.73825 1.28619 8.56981 1.17325C8.40137 1.06031 8.20315 1 8.00035 1C7.79756 1 7.59934 1.06031 7.4309 1.17325C7.26246 1.28619 7.13141 1.44667 7.05442 1.63429L5.63192 5.07679L1.94254 5.37491C1.74078 5.39198 1.54854 5.4682 1.3899 5.59404C1.23127 5.71988 1.1133 5.88973 1.05077 6.08232C0.988239 6.27491 0.983936 6.48167 1.0384 6.67669C1.09286 6.87172 1.20366 7.04633 1.35692 7.17866L4.16942 9.60554L3.31254 13.2343C3.26462 13.4314 3.27635 13.6384 3.34625 13.8288C3.41615 14.0193 3.54107 14.1847 3.70514 14.304C3.86921 14.4234 4.06505 14.4913 4.26778 14.4991C4.47051 14.5069 4.671 14.4544 4.84379 14.348L8.00004 12.4055L11.1582 14.348C11.331 14.4531 11.5311 14.5047 11.7332 14.4962C11.9353 14.4878 12.1304 14.4198 12.2939 14.3007C12.4574 14.1816 12.5821 14.0168 12.6521 13.8271C12.7221 13.6373 12.7345 13.431 12.6875 13.2343L11.8275 9.60491L14.64 7.17804C14.7945 7.04593 14.9064 6.87094 14.9613 6.67522C15.0163 6.47951 15.0119 6.27189 14.9488 6.07866ZM13.99 6.42054L10.9463 9.04554C10.8769 9.10537 10.8252 9.18312 10.797 9.27031C10.7688 9.3575 10.7651 9.45076 10.7863 9.53991L11.7163 13.4649C11.7187 13.4703 11.7189 13.4765 11.717 13.482C11.715 13.4876 11.7109 13.4922 11.7057 13.4949C11.6944 13.5037 11.6913 13.5018 11.6819 13.4949L8.26192 11.3918C8.18315 11.3434 8.0925 11.3177 8.00004 11.3177C7.90758 11.3177 7.81693 11.3434 7.73817 11.3918L4.31817 13.4962C4.30879 13.5018 4.30629 13.5037 4.29442 13.4962C4.28914 13.4935 4.2851 13.4889 4.28312 13.4833C4.28115 13.4777 4.28139 13.4716 4.28379 13.4662L5.21379 9.54116C5.23499 9.45201 5.23127 9.35875 5.20306 9.27156C5.17484 9.18437 5.1232 9.10662 5.05379 9.04679L2.01004 6.42179C2.00254 6.41554 1.99567 6.40991 2.00192 6.39054C2.00817 6.37116 2.01317 6.37366 2.02254 6.37241L6.01754 6.04991C6.10917 6.04205 6.19686 6.00907 6.27096 5.9546C6.34506 5.90013 6.4027 5.82628 6.43754 5.74116L7.97629 2.01554C7.98129 2.00491 7.99817 1.99991 7.99817 1.99991C7.99817 1.99991 8.01504 2.00491 8.02004 2.01554L9.56254 5.74116C9.59771 5.82631 9.65572 5.90008 9.73016 5.95434C9.80461 6.00861 9.89259 6.04125 9.98442 6.04866L13.9794 6.37116C13.9888 6.37116 13.9944 6.37116 14 6.38929C14.0057 6.40741 14 6.41429 13.99 6.42054Z" fill={STAR_FILL} />
              <path fillRule="evenodd" clipRule="evenodd" d="M8.00004 11.3177C7.90758 11.3177 7.81693 11.3434 7.73817 11.3918L4.31817 13.4962C4.30879 13.5018 4.30629 13.5037 4.29442 13.4962C4.28914 13.4935 4.2851 13.4889 4.28312 13.4833C4.28115 13.4777 4.28139 13.4716 4.28379 13.4662L5.21379 9.54116C5.23499 9.45201 5.23127 9.35875 5.20306 9.27156C5.17484 9.18437 5.1232 9.10662 5.05379 9.04679L2.01004 6.42179C2.00254 6.41554 1.99567 6.40991 2.00192 6.39054C2.00733 6.37377 2.01536 6.37302 2.02254 6.37241C2.02128 6.37258 2.02366 6.37232 2.02254 6.37241L6.01754 6.04991C6.10917 6.04205 6.19686 6.00907 6.27096 5.9546C6.34506 5.90013 6.4027 5.82628 6.43754 5.74116L7.97629 2.01554C7.98129 2.00491 7.99817 1.99991 7.99817 1.99991L8.00004 11.3177Z" fill={STAR_FILL} />
            </svg>
          )}
          {t === 'empty' && (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M14.9488 6.07866C14.8863 5.88649 14.7683 5.71712 14.6097 5.59189C14.4511 5.46665 14.259 5.39116 14.0575 5.37491L10.37 5.07741L8.94629 1.63429C8.8693 1.44667 8.73825 1.28619 8.56981 1.17325C8.40137 1.06031 8.20315 1 8.00035 1C7.79756 1 7.59934 1.06031 7.4309 1.17325C7.26246 1.28619 7.13141 1.44667 7.05442 1.63429L5.63192 5.07679L1.94254 5.37491C1.74078 5.39198 1.54854 5.4682 1.3899 5.59404C1.23127 5.71988 1.1133 5.88973 1.05077 6.08232C0.988239 6.27491 0.983936 6.48167 1.0384 6.67669C1.09286 6.87172 1.20366 7.04633 1.35692 7.17866L4.16942 9.60554L3.31254 13.2343C3.26462 13.4314 3.27635 13.6384 3.34625 13.8288C3.41615 14.0193 3.54107 14.1847 3.70514 14.304C3.86921 14.4234 4.06505 14.4913 4.26778 14.4991C4.47051 14.5069 4.671 14.4544 4.84379 14.348L8.00004 12.4055L11.1582 14.348C11.331 14.4531 11.5311 14.5047 11.7332 14.4962C11.9353 14.4878 12.1304 14.4198 12.2939 14.3007C12.4574 14.1816 12.5821 14.0168 12.6521 13.8271C12.7221 13.6373 12.7345 13.431 12.6875 13.2343L11.8275 9.60491L14.64 7.17804C14.7945 7.04593 14.9064 6.87094 14.9613 6.67522C15.0163 6.47951 15.0119 6.27189 14.9488 6.07866ZM13.99 6.42054L10.9463 9.04554C10.8769 9.10537 10.8252 9.18312 10.797 9.27031C10.7688 9.3575 10.7651 9.45076 10.7863 9.53991L11.7163 13.4649C11.7187 13.4703 11.7189 13.4765 11.717 13.482C11.715 13.4876 11.7109 13.4922 11.7057 13.4949C11.6944 13.5037 11.6913 13.5018 11.6819 13.4949L8.26192 11.3918C8.18315 11.3434 8.0925 11.3177 8.00004 11.3177C7.90758 11.3177 7.81693 11.3434 7.73817 11.3918L4.31817 13.4962C4.30879 13.5018 4.30629 13.5037 4.29442 13.4962C4.28914 13.4935 4.2851 13.4889 4.28312 13.4833C4.28115 13.4777 4.28139 13.4716 4.28379 13.4662L5.21379 9.54116C5.23499 9.45201 5.23127 9.35875 5.20306 9.27156C5.17484 9.18437 5.1232 9.10662 5.05379 9.04679L2.01004 6.42179C2.00254 6.41554 1.99567 6.40991 2.00192 6.39054C2.00817 6.37116 2.01317 6.37366 2.02254 6.37241L6.01754 6.04991C6.10917 6.04205 6.19686 6.00907 6.27096 5.9546C6.34506 5.90013 6.4027 5.82628 6.43754 5.74116L7.97629 2.01554C7.98129 2.00491 7.98317 1.99991 7.99817 1.99991C8.01317 1.99991 8.01504 2.00491 8.02004 2.01554L9.56254 5.74116C9.59771 5.82631 9.65572 5.90008 9.73016 5.95434C9.80461 6.00861 9.89259 6.04125 9.98442 6.04866L13.9794 6.37116C13.9888 6.37116 13.9944 6.37116 14 6.38929C14.0057 6.40741 14 6.41429 13.99 6.42054Z" fill={STAR_FILL} />
            </svg>
          )}
        </span>
      ))}
    </span>
  );
}

export default function ItemReviewsPage() {
  const { itemId } = useParams();
  const navigate = useNavigate();
  const { setTabBarVisible } = useTabBarVisibility();
  const [summary, setSummary] = useState({ average_rating: 0, total_count: 0 });
  const [reviewsList, setReviewsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterOpen, setFilterOpen] = useState(false);
  const [sort, setSort] = useState('date_desc');
  const [stars, setStars] = useState(null);
  const [draftSort, setDraftSort] = useState('date_desc');
  const [draftStars, setDraftStars] = useState(null);
  const filterPanelRef = useRef(null);
  const [photoGallery, setPhotoGallery] = useState(null);

  useEffect(() => {
    setTabBarVisible(false);
    const tg = window.Telegram?.WebApp;
    const back = tg?.BackButton;
    if (!back) return () => setTabBarVisible(true);
    const onBack = () => navigate(-1);
    back.onClick(onBack);
    back.show();
    return () => { back.offClick(onBack); back.hide(); setTabBarVisible(true); };
  }, [navigate, setTabBarVisible]);

  useEffect(() => {
    if (!itemId) return;
    let c = false;
    getItemReviewsSummary(itemId).then((d) => { if (!c) setSummary(d || { average_rating: 0, total_count: 0 }); }).catch(() => {});
    return () => { c = true; };
  }, [itemId]);

  useEffect(() => {
    if (!itemId) return;
    setLoading(true);
    getItemReviews(itemId, { sort, stars: stars ?? undefined, limit: 50, offset: 0 })
      .then((d) => setReviewsList(Array.isArray(d?.reviews) ? d.reviews : []))
      .catch(() => setReviewsList([]))
      .finally(() => setLoading(false));
  }, [itemId, sort, stars]);

  useEffect(() => {
    if (!filterOpen) return;
    const onOutside = (e) => {
      if (filterPanelRef.current && !filterPanelRef.current.contains(e.target)) setFilterOpen(false);
    };
    document.addEventListener('click', onOutside, true);
    return () => document.removeEventListener('click', onOutside, true);
  }, [filterOpen]);

  const applyFilter = useCallback(() => {
    setSort(draftSort);
    setStars(draftStars);
    setFilterOpen(false);
  }, [draftSort, draftStars]);

  const openFilter = useCallback(() => {
    setDraftSort(sort);
    setDraftStars(stars);
    setFilterOpen(true);
  }, [sort, stars]);

  const total = summary.total_count || 0;

  return (
    <div className="reviews-page page-container">
      <header className="reviews-page__header">
        <div className="reviews-page__title-row">
          <div className="reviews-page__title-pill" aria-hidden="true">
            Отзывы {total}
          </div>
          <button type="button" className="reviews-page__filter-btn" aria-label="Фильтры" onClick={openFilter}>
            <svg width="20" height="20" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M28.825 6.19128C28.6711 5.83567 28.416 5.53315 28.0915 5.32135C27.767 5.10955 27.3875 4.99781 27 5.00003H4.99997C4.61288 5.0008 4.23433 5.11387 3.91025 5.32554C3.58616 5.53721 3.33047 5.83838 3.17418 6.19251C3.01789 6.54664 2.96772 6.93852 3.02977 7.3206C3.09181 7.70268 3.2634 8.05855 3.52372 8.34503L3.53372 8.35628L12 17.3963V27C11.9999 27.362 12.098 27.7172 12.284 28.0278C12.4699 28.3384 12.7366 28.5927 13.0557 28.7636C13.3748 28.9345 13.7343 29.0155 14.0958 28.9982C14.4574 28.9808 14.8075 28.8657 15.1087 28.665L19.1087 25.9975C19.3829 25.8149 19.6078 25.5673 19.7632 25.2769C19.9187 24.9864 20 24.662 20 24.3325V17.3963L28.4675 8.35628L28.4775 8.34503C28.7405 8.05986 28.9138 7.70352 28.9756 7.32049C29.0374 6.93747 28.985 6.54472 28.825 6.19128ZM18.2725 16.3225C18.0995 16.5059 18.0021 16.7479 18 17V24.3325L14 27V17C14 16.7461 13.9035 16.5017 13.73 16.3163L4.99997 7.00003H27L18.2725 16.3225Z" fill="currentColor" />
            </svg>
          </button>
        </div>
        {total > 0 && (
          <div className="reviews-page__rating-wrap">
            <div className="reviews-page__average reviews-page__average--header">
              <span className="reviews-page__average-value">{Number(summary.average_rating).toFixed(2)}</span>
              <div className="reviews-page__average-stars-block">
                <StarRating rating={summary.average_rating} className="reviews-page__average-stars" />
                <span className="reviews-page__average-label">Мнение покупателей</span>
              </div>
            </div>
          </div>
        )}
        {filterOpen && (
          <div ref={filterPanelRef} className="reviews-page__filter-panel" onClick={(e) => e.stopPropagation()}>
            <div className="reviews-page__filter-row">
              <label className="reviews-page__filter-label">Сортировка</label>
              <div className="reviews-page__filter-btns">
                <button type="button" className={`reviews-page__filter-btn-opt ${draftSort === 'date_desc' ? 'reviews-page__filter-btn-opt--active' : ''}`} onClick={() => setDraftSort('date_desc')}>Сначала новые</button>
                <button type="button" className={`reviews-page__filter-btn-opt ${draftSort === 'date_asc' ? 'reviews-page__filter-btn-opt--active' : ''}`} onClick={() => setDraftSort('date_asc')}>Сначала старые</button>
              </div>
            </div>
            <div className="reviews-page__filter-row">
              <label className="reviews-page__filter-label">Оценка</label>
              <div className="reviews-page__filter-stars">
                {[null, 5, 4, 3, 2, 1].map((s) => (
                  <button key={s ?? 'all'} type="button" className={`reviews-page__filter-star-opt ${draftStars === s ? 'reviews-page__filter-star-opt--active' : ''}`} onClick={() => setDraftStars(s)}>{s == null ? 'Все' : `${s} ★`}</button>
                ))}
              </div>
            </div>
            <button type="button" className="reviews-page__filter-apply" onClick={applyFilter}>Применить</button>
          </div>
        )}
      </header>

      {(sort !== 'date_desc' || stars != null) && (
        <div className="reviews-page__chips">
          {sort !== 'date_desc' && <div className="reviews-page__chip"><span>Сначала старые</span><button type="button" onClick={() => setSort('date_desc')} aria-label="Сбросить" /></div>}
          {stars != null && <div className="reviews-page__chip"><span>{stars} ★</span><button type="button" onClick={() => setStars(null)} aria-label="Сбросить" /></div>}
        </div>
      )}

      {loading ? (
        <div className="reviews-page__loading">Загрузка отзывов…</div>
      ) : reviewsList.length > 0 ? (
        <div className="reviews-page__list">
          {reviewsList.map((rev) => (
            <div key={rev.id} className="reviews-page__card">
              <div className="reviews-page__card-top">
                <StarRating rating={rev.rating} className="reviews-page__card-stars" />
                <span className="reviews-page__card-date">{rev.created_at ? new Date(rev.created_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''}</span>
              </div>
              <div className="reviews-page__card-user">
                <AvatarWithFallback
                  src={rev.user_avatar_url}
                  seed={rev.user_id}
                  className="reviews-page__card-avatar"
                  alt=""
                />
                <span className="reviews-page__card-name">{rev.user_name || 'Пользователь'}</span>
              </div>
              {rev.comment ? <p className="reviews-page__card-comment">{rev.comment}</p> : null}
              {Array.isArray(rev.photos) && rev.photos.length > 0 && (
                <div className="reviews-page__card-photos">
                  {rev.photos.slice(0, 3).map((path, idx) => (
                    <button key={idx} type="button" className={`reviews-page__card-photo ${idx === 2 && rev.photos.length > 3 ? 'reviews-page__card-photo--with-more' : ''}`} onClick={() => setPhotoGallery({ photos: rev.photos, currentIndex: idx })}>
                      <img src={`/${path}`} alt="" className={idx === 2 && rev.photos.length > 3 ? 'reviews-page__card-photo-img--blur' : ''} />
                      {idx === 2 && rev.photos.length > 3 && (
                        <span className="reviews-page__card-photo-more">+{rev.photos.length - 3}</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : total === 0 ? null : (
        <div className="reviews-page__empty">Нет отзывов по выбранным фильтрам</div>
      )}

      {photoGallery && (
        <PhotoGalleryModal photos={photoGallery.photos} currentIndex={photoGallery.currentIndex} onClose={() => setPhotoGallery(null)} />
      )}
    </div>
  );
}
