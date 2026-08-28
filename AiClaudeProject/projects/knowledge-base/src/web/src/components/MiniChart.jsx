/**
 * MiniChart.jsx - 迷你 SVG 折线图
 *
 * 用于在右侧面板展示数据趋势的小型图表
 */
import React from 'react';

function MiniChart({ data, color = '#0D9488', height = 50 }) {
  if (!data || data.length < 2) return null;
  const maxVal = Math.max(...data.map(d => d.value || 0));
  const minVal = Math.min(...data.map(d => d.value || 0));
  const range = maxVal - minVal || 1;
  const w = 120;
  const h = height;
  const stepX = w / Math.max(data.length - 1, 1);
  const points = data.map((d, i) => {
    const x = i * stepX;
    const y = h - (((d.value || 0) - minVal) / range) * (h - 16);
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {data.map((d, i) => {
        const x = i * stepX;
        const y = h - (((d.value || 0) - minVal) / range) * (h - 16);
        return <circle key={i} cx={x} cy={y} r="2.5" fill={color} stroke="#fff" strokeWidth="1.5" />;
      })}
    </svg>
  );
}

export default MiniChart;