import React, { useEffect, useMemo, useState } from 'react';
import { ensureHttps } from '../../utils/url';
import { fallbackAvatarUrl } from '../../utils/fallbackAvatar';

/**
 * Аватар: основной src с бэка; при отсутствии или ошибке загрузки — локальная заглушка.
 */
export default function AvatarWithFallback({ src, seed, className, alt = '' }) {
  const fallbackSrc = useMemo(() => fallbackAvatarUrl(seed), [seed]);
  const primary = src && String(src).trim() ? ensureHttps(src) : null;
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    setBroken(false);
  }, [primary]);

  const useFallback = !primary || broken;
  const imgSrc = useFallback ? fallbackSrc : primary;

  return (
    <img
      src={imgSrc}
      alt={alt}
      className={className}
      onError={() => {
        if (!useFallback) setBroken(true);
      }}
    />
  );
}
