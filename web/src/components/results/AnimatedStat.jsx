import { useEffect, useRef, useState } from 'react';
import { formatNumber } from '../../utils/formatters.js';

/**
 * AnimatedStat — big number that counts up from 0 to the target value.
 */
export default function AnimatedStat({ value, label }) {
  const [display, setDisplay] = useState('0');
  const frameRef = useRef(null);

  useEffect(() => {
    const num = typeof value === 'number' ? value : parseFloat(value);
    if (isNaN(num)) {
      setDisplay(String(value));
      return;
    }

    const duration = 1500;
    const startTime = performance.now();
    const isFloat = !Number.isInteger(num);

    const animate = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      /* ease-out cubic */
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = num * eased;

      setDisplay(formatNumber(current, isFloat ? 2 : 0));

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate);
      }
    };

    frameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameRef.current);
  }, [value]);

  return (
    <div className="animated-stat">
      <div className="animated-stat__value">{display}</div>
      {label && <div className="animated-stat__label">{label}</div>}
    </div>
  );
}
