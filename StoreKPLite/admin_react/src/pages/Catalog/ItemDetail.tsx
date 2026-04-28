import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import { getTelegramCaptionLength, TELEGRAM_CAPTION_MAX_LENGTH } from '../../utils/telegramUtils';
import './Catalog.css';

interface ItemDetail {
  id: number;
  name: string;
  description: string | null;
  price: number;
  service_fee_percent: number;
  estimated_weight_kg: number | null;
  length_cm: number | null;
  width_cm: number | null;
  height_cm: number | null;
  item_type_id: number;
  item_type: string;
  gender: string;
  size: string[] | null;
  link: string | null;
  is_legit: boolean | null;
  fixed_price: number | null;
  group_id: number | null;
  current_price_rub: number | null;
  service_fee_amount: number | null;
  photos: Array<{
    id: number;
    file_path: string;
    telegram_file_id: string | null;
    vk_attachment: string | null;
  }>;
}

const ItemDetail: React.FC = () => {
  const { itemId } = useParams<{ itemId: string }>();
  const navigate = useNavigate();
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [shareLink, setShareLink] = useState('');
  const [showPostModal, setShowPostModal] = useState(false);
  const [postText, setPostText] = useState('');
  const [postPhotoIds, setPostPhotoIds] = useState<number[]>([]);
  const [additionalPostFiles, setAdditionalPostFiles] = useState<File[]>([]);
  const [posting, setPosting] = useState(false);
  const BOT_USERNAME = process.env.REACT_APP_TELEGRAM_BOT_USERNAME || '';

  useEffect(() => {
    if (itemId) {
      fetchItem(parseInt(itemId));
    }
  }, [itemId]);

  useEffect(() => {
    if (item) {
      setShareLink(`https://t.me/${BOT_USERNAME}?startapp=item_${item.id}`);
    }
  }, [item]);

  const fetchItem = async (id: number) => {
    try {
      setLoading(true);
      const response = await apiClient.get(`/products/admin/items/${id}`);
      setItem(response.data);
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Товар не найден');
      console.error('Ошибка загрузки товара:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!item || !window.confirm('Вы уверены, что хотите удалить этот товар?')) {
      return;
    }

    try {
      await apiClient.delete(`/products/admin/items/${item.id}`);
      navigate('/catalog');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления товара');
      console.error('Ошибка удаления:', err);
    }
  };

  const copyShareLink = () => {
    navigator.clipboard.writeText(shareLink).then(() => {
      alert('Ссылка скопирована!');
    }).catch(() => {
      alert('Не удалось скопировать ссылку');
    });
  };

  const generatePostTemplate = (item: ItemDetail): string => {
    const priceValue = item.current_price_rub != null
      ? (typeof item.current_price_rub === 'number' ? item.current_price_rub.toFixed(2) : Number(item.current_price_rub).toFixed(2))
      : '';
    const sizeText = item.size && Array.isArray(item.size)
      ? `(${item.size.join(', ')})`
      : '(Не указан)';
    const itemLink = `https://t.me/${BOT_USERNAME}?startapp=item_${item.id}`;
    const typeHashtag = item.item_type ? `#${item.item_type.replace(/\s+/g, '_')}` : '';

    return `${item.name} 🖤

Размеры: ${sizeText}

Доставка по всей России 🌎
Личная встреча г. Уссурийск

💰 ${priceValue ? `~${priceValue} ₽\n(актуальная цена в боте)` : 'Цена в боте'}

<a href="https://t.me/Timoshka_otzivi">ОТЗЫВЫ</a>

🛒 Добавить в корзину:
${itemLink}

💬 Вопросы? В боте: Поддержка → FAQ${typeHashtag ? `\n\n${typeHashtag}` : ''}`;
  };

  const handleOpenPostModal = () => {
    if (item) {
      const template = generatePostTemplate(item);
      setPostText(template);
      const withFileId = item.photos.filter((p) => p.telegram_file_id).map((p) => p.id);
      setPostPhotoIds(withFileId);
      setShowPostModal(true);
    }
  };

  const handleClosePostModal = () => {
    setShowPostModal(false);
    setPostText('');
    setPostPhotoIds([]);
    setAdditionalPostFiles([]);
    setError('');
  };

  const togglePostPhoto = (photoId: number) => {
    setPostPhotoIds((prev) =>
      prev.includes(photoId)
        ? prev.filter((id) => id !== photoId)
        : [...prev, photoId]
    );
  };

  const movePostPhoto = (fromIndex: number, direction: 'up' | 'down') => {
    setPostPhotoIds((prev) => {
      if (direction === 'up' && fromIndex <= 0) return prev;
      if (direction === 'down' && fromIndex >= prev.length - 1) return prev;
      const toIndex = direction === 'up' ? fromIndex - 1 : fromIndex + 1;
      const arr = [...prev];
      [arr[fromIndex], arr[toIndex]] = [arr[toIndex], arr[fromIndex]];
      return arr;
    });
  };

  const moveAdditionalPhoto = (fromIndex: number, direction: 'up' | 'down') => {
    setAdditionalPostFiles((prev) => {
      if (direction === 'up' && fromIndex <= 0) return prev;
      if (direction === 'down' && fromIndex >= prev.length - 1) return prev;
      const toIndex = direction === 'up' ? fromIndex - 1 : fromIndex + 1;
      const arr = [...prev];
      [arr[fromIndex], arr[toIndex]] = [arr[toIndex], arr[fromIndex]];
      return arr;
    });
  };

  const handlePostToTelegram = async () => {
    if (!item || !postText.trim()) {
      setError('Текст поста не может быть пустым');
      return;
    }

    const captionLen = getTelegramCaptionLength(postText);
    if (captionLen > TELEGRAM_CAPTION_MAX_LENGTH) {
      setError(`Текст поста превышает лимит (${captionLen} > ${TELEGRAM_CAPTION_MAX_LENGTH} символов после форматирования)`);
      return;
    }

    const totalPhotos = postPhotoIds.length + additionalPostFiles.length;
    if (totalPhotos === 0) {
      setError('Выберите фото из каталога или загрузите свои');
      return;
    }
    if (totalPhotos > 10) {
      setError('Максимум 10 фото в посте');
      return;
    }

    try {
      setPosting(true);
      setError('');
      const orderedPhotoIds = [...postPhotoIds];
      const form = new FormData();
      form.append('message_text', postText);
      form.append('photo_ids', JSON.stringify(orderedPhotoIds));
      additionalPostFiles.forEach((f) => form.append('additional_photos', f));
      const response = await apiClient.post(
        `/products/admin/items/${item.id}/post-to-telegram`,
        form
      );
      alert('Пост успешно отправлен в Telegram канал!');
      handleClosePostModal();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка при отправке поста');
      console.error('Ошибка отправки поста:', err);
    } finally {
      setPosting(false);
    }
  };

  if (loading) {
    return <div className="catalog-page">Загрузка...</div>;
  }

  if (error && !item) {
    return (
      <div className="catalog-page">
        <div className="error-message">{error}</div>
        <button onClick={() => navigate('/catalog')} className="btn-view">
          Назад к списку
        </button>
      </div>
    );
  }

  if (!item) {
    return null;
  }

  return (
    <div className="catalog-page">
      <div className="item-detail-header">
        <h1>{item.name}</h1>
        <div className="item-detail-actions">
          <button onClick={handleOpenPostModal} className="btn-primary">
            📢 Сделать пост
          </button>
          <button onClick={() => navigate(`/catalog/${item.id}/edit`)} className="btn-edit">
            Редактировать
          </button>
          <button onClick={handleDelete} className="btn-delete">
            Удалить
          </button>
          <button onClick={() => navigate('/catalog')} className="btn-secondary">
            Назад к списку
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="share-section">
        <h2>📤 Поделись этим товаром:</h2>
        <div className="share-link-container">
          <input
            type="text"
            value={shareLink}
            readOnly
            onClick={(e) => (e.target as HTMLInputElement).select()}
          />
          <button onClick={copyShareLink} className="btn-primary">
            📋 Копировать
          </button>
        </div>
        <p className="share-hint">
          Скопируйте ссылку и отправьте её пользователям, чтобы они могли перейти к этому товару в боте.
        </p>
      </div>

      <div className="item-detail-card">
        <h2>Информация о товаре</h2>
        <div className="detail-row">
          <label>Название:</label>
          <div>{item.name}</div>
        </div>
        <div className="detail-row">
          <label>Описание:</label>
          <div>{item.description || 'Не указано'}</div>
        </div>
        <div className="detail-row">
          <label>Цена (₽):</label>
          <div>{item.fixed_price != null ? `${item.fixed_price} ₽` : `${item.price} ₽`}</div>
        </div>
        <div className="detail-row">
          <label>Вес посылки:</label>
          <div>{item.estimated_weight_kg ? `${item.estimated_weight_kg} кг` : 'Не указан'}</div>
        </div>
        <div className="detail-row">
          <label>Габариты (см):</label>
          <div>
            {item.length_cm != null && item.width_cm != null && item.height_cm != null
              ? `${item.length_cm} × ${item.width_cm} × ${item.height_cm}`
              : 'Не указаны'}
          </div>
        </div>
        <div className="detail-row">
          <label>Тип:</label>
          <div>{item.item_type}</div>
        </div>
        <div className="detail-row">
          <label>Пол:</label>
          <div>{item.gender}</div>
        </div>
        <div className="detail-row">
          <label>Размеры:</label>
          <div>{item.size && Array.isArray(item.size) ? item.size.join(', ') : (item.size || 'Не указан')}</div>
        </div>
        <div className="detail-row">
          <label>Оригинал / реплика:</label>
          <div>{item.is_legit === true ? 'Оригинал' : item.is_legit === false ? 'Реплика' : 'Не указано'}</div>
        </div>
        <div className="detail-row">
          <label>Фиксированная цена (₽):</label>
          <div>{item.fixed_price != null ? `${item.fixed_price} ₽` : `${item.price} ₽`}</div>
        </div>
        {item.group_id != null && (
          <div className="detail-row">
            <label>Группа товаров (ID):</label>
            <div>{item.group_id}</div>
          </div>
        )}
        <div className="detail-row">
          <label>Ссылка:</label>
          <div>
            {item.link ? (
              <a href={item.link} target="_blank" rel="noopener noreferrer" style={{ color: '#3498db' }}>
                {item.link}
              </a>
            ) : (
              'Не указана'
            )}
          </div>
        </div>
      </div>

      <div className="item-photos-section">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0 }}>Фотографии</h2>
          <button
            onClick={async () => {
              if (window.confirm('Обновить file_id и attachment для всех фотографий каталога? Это может занять некоторое время.')) {
                try {
                  setError('');
                  const response = await apiClient.post('/products/admin/items/photos/update-ids');
                  const result = response.data;
                  alert(
                    `Обновление завершено!\n` +
                    `Обновлено фотографий: ${result.updated_count}\n` +
                    `Telegram file_id: ${result.telegram_updated}\n` +
                    `VK attachment: ${result.vk_updated}`
                  );
                  // Обновляем данные товара, чтобы увидеть изменения
                  fetchItem(item.id);
                } catch (err: any) {
                  setError(err.response?.data?.detail || 'Ошибка обновления фотографий');
                }
              }
            }}
            className="btn btn-primary"
            style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}
          >
            🔄 Обновить фото каталога
          </button>
        </div>
        {item.photos && item.photos.length > 0 ? (
          <div className="photos-grid">
            {item.photos.map((photo) => (
              <div key={photo.id} className="photo-item">
                <img
                  src={`/${photo.file_path}`}
                  alt={item.name}
                  onClick={() => window.open(`${window.location.origin}/${photo.file_path}`, '_blank')}
                  onError={(e) => {
                    (e.target as HTMLImageElement).src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="200"%3E%3Crect width="200" height="200" fill="%23f0f0f0"/%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" dy=".3em" fill="%23999"%3EИзображение не найдено%3C/text%3E%3C/svg%3E';
                  }}
                />
                <button
                  onClick={async () => {
                    if (window.confirm('Удалить эту фотографию?')) {
                      try {
                        await apiClient.delete(`/products/admin/items/photos/${photo.id}`);
                        fetchItem(item.id);
                      } catch (err: any) {
                        setError(err.response?.data?.detail || 'Ошибка удаления фотографии');
                      }
                    }
                  }}
                  className="btn-delete"
                >
                  Удалить
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p>Фотографий пока нет.</p>
        )}
      </div>

      {/* Модальное окно для создания поста */}
      {showPostModal && (
        <div className="modal-overlay" onClick={handleClosePostModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Создать пост</h2>
              <button className="modal-close" onClick={handleClosePostModal}>×</button>
            </div>
            <div className="modal-body">
              {error && <div className="error-message">{error}</div>}
              <div className="form-group">
                <label>Фото в пост (макс. 10 всего)</label>
                {item.photos.filter((p) => p.telegram_file_id).length > 0 && (
                  <>
                  <small style={{ display: 'block', marginBottom: '0.5rem', color: '#666' }}>
                    Из каталога (галочка — включить, ↑↓ — порядок отправки):
                  </small>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem', alignItems: 'flex-start' }}>
                    {[
                      ...postPhotoIds.map((id) => item.photos.find((p) => p.id === id)).filter(Boolean),
                      ...item.photos.filter((p) => p.telegram_file_id && !postPhotoIds.includes(p.id)),
                    ].map((photo) => {
                      if (!photo) return null;
                      const isSelected = postPhotoIds.includes(photo.id);
                      const idx = postPhotoIds.indexOf(photo.id);
                      return (
                        <div key={photo.id} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px', opacity: isSelected ? 1 : 0.5 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <label style={{ cursor: 'pointer' }}>
                              <input type="checkbox" checked={isSelected} onChange={() => togglePostPhoto(photo.id)} style={{ width: 16, height: 16, accentColor: '#4caf50' }} />
                              <img src={`/${photo.file_path}`} alt="" style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: '8px', marginLeft: 4, border: isSelected ? '2px solid #4caf50' : '2px solid transparent', display: 'block' }} />
                            </label>
                            {isSelected && (
                              <div style={{ display: 'flex', flexDirection: 'column' }}>
                                <button type="button" onClick={() => movePostPhoto(idx, 'up')} disabled={idx === 0} style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: 1 }} title="Выше">↑</button>
                                <button type="button" onClick={() => movePostPhoto(idx, 'down')} disabled={idx === postPhotoIds.length - 1} style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: 1 }} title="Ниже">↓</button>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  </>
                )}
                <div style={{ marginTop: '1rem' }}>
                  <label style={{ display: 'block', marginBottom: '0.5rem', color: '#666' }}>
                    Догрузить свои фото:
                  </label>
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/gif,image/webp"
                    multiple
                    onChange={(e) => {
                      const files = Array.from(e.target.files || []);
                      setAdditionalPostFiles((prev) => {
                        const combined = [...prev, ...files];
                        if (combined.length + postPhotoIds.length > 10) {
                          return combined.slice(0, 10 - postPhotoIds.length);
                        }
                        return combined;
                      });
                      e.target.value = '';
                    }}
                    style={{ fontSize: '0.9rem' }}
                  />
                  {additionalPostFiles.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem', alignItems: 'flex-start' }}>
                      {additionalPostFiles.map((f, i) => (
                        <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', position: 'relative', border: '2px solid #4caf50', borderRadius: '8px', padding: '4px' }}>
                            <img src={URL.createObjectURL(f)} alt="" style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: '4px' }} />
                            <span style={{ fontSize: '0.75rem', maxWidth: 70, overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.name}</span>
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                              <button type="button" onClick={() => moveAdditionalPhoto(i, 'up')} disabled={i === 0} style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: 1 }} title="Выше">↑</button>
                              <button type="button" onClick={() => moveAdditionalPhoto(i, 'down')} disabled={i === additionalPostFiles.length - 1} style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: 1 }} title="Ниже">↓</button>
                            </div>
                            <button type="button" onClick={() => setAdditionalPostFiles((prev) => prev.filter((_, idx) => idx !== i))} style={{ position: 'absolute', top: 2, right: 2, background: '#f44336', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.7rem', padding: '2px 6px' }}>×</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  <small style={{ display: 'block', marginTop: '0.25rem', color: '#666' }}>
                    Порядок: каталог (↑↓), затем свои фото (↑↓). Всего {postPhotoIds.length + additionalPostFiles.length} / 10
                  </small>
                </div>
              </div>
              <div className="form-group">
                <label>Текст поста (макс. {TELEGRAM_CAPTION_MAX_LENGTH} символов после форматирования)</label>
                <textarea
                  value={postText}
                  onChange={(e) => {
                    setPostText(e.target.value);
                    setError('');
                  }}
                  rows={12}
                  className="post-textarea"
                  placeholder="Введите текст поста..."
                />
                <small className="char-count">
                  {getTelegramCaptionLength(postText)} / {TELEGRAM_CAPTION_MAX_LENGTH} символов
                </small>
              </div>
            </div>
            <div className="modal-footer">
              <button
                onClick={handlePostToTelegram}
                className="btn-primary"
                disabled={posting || !postText.trim() || getTelegramCaptionLength(postText) > TELEGRAM_CAPTION_MAX_LENGTH || (postPhotoIds.length === 0 && additionalPostFiles.length === 0) || postPhotoIds.length + additionalPostFiles.length > 10}
              >
                {posting ? 'Отправка...' : '📢 Сделать пост в ТГК'}
              </button>
              <button
                className="btn-secondary"
                disabled={true}
                style={{ opacity: 0.5, cursor: 'not-allowed' }}
                title="Функция пока не реализована"
              >
                📢 Сделать пост в ВК
              </button>
              <button onClick={handleClosePostModal} className="btn-secondary">
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ItemDetail;

