import React from 'react';
import './ProfileAvatarEditorModal.css';

/**
 * Предпросмотр квадратного аватара перед загрузкой (без интерактивного кропа).
 */
export default function ProfileAvatarEditorModal({
  previewUrl,
  uploading,
  errorText,
  onClose,
  onConfirm,
}) {
  return (
    <div
      className="profile-avatar-modal__backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="profile-avatar-modal-title"
      onClick={onClose}
    >
      <div className="profile-avatar-modal__dialog" onClick={(e) => e.stopPropagation()}>
        <h2 id="profile-avatar-modal-title" className="profile-avatar-modal__title">
          Фото профиля
        </h2>
        <div className="profile-avatar-modal__preview-wrap">
          {previewUrl ? (
            <img src={previewUrl} alt="" className="profile-avatar-modal__preview-img" />
          ) : null}
        </div>
        {errorText ? <p className="profile-avatar-modal__err">{errorText}</p> : null}
        <div className="profile-avatar-modal__actions">
          <button
            type="button"
            className="profile-avatar-modal__btn profile-avatar-modal__btn--primary"
            onClick={onConfirm}
            disabled={uploading || !previewUrl}
          >
            {uploading ? 'Загрузка…' : 'Сохранить'}
          </button>
          <button
            type="button"
            className="profile-avatar-modal__btn profile-avatar-modal__btn--ghost"
            onClick={onClose}
            disabled={uploading}
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}
