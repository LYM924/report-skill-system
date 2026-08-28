/**
 * SimpleMarkdown.jsx - 简单 Markdown 渲染组件
 *
 * 支持标题、列表、表格、图片、链接、粗体、代码块、引用等
 * 自动跳过前导 YAML frontmatter 块
 */
import React from 'react';
import { Typography, Image } from 'antd';

const { Text } = Typography;

function SimpleMarkdown({ content, isDark }) {
  if (!content) return <Text type="secondary">暂无内容</Text>;

  /** 渲染行内元素：图片、链接、粗体、行内代码、删除线 */
  function renderInline(text) {
    if (!text) return text;
    const parts = [];
    let remaining = text;
    let key = 0;

    const pattern = /!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`|~~([^~]+)~~/g;
    let lastIndex = 0;
    let match;

    while ((match = pattern.exec(remaining)) !== null) {
      if (match.index > lastIndex) {
        parts.push(remaining.slice(lastIndex, match.index));
      }

      if (match[1] !== undefined) {
        parts.push(
          <Image key={key++} src={match[2]} alt={match[1]}
            style={{ maxWidth: '100%', borderRadius: 6, margin: '8px 0' }} />
        );
      } else if (match[3] !== undefined) {
        parts.push(
          <a key={key++} href={match[4]} target="_blank" rel="noopener noreferrer" style={{ color: '#0D9488' }}>{match[3]}</a>
        );
      } else if (match[5] !== undefined) {
        parts.push(<strong key={key++}>{match[5]}</strong>);
      } else if (match[6] !== undefined) {
        parts.push(<code key={key++} style={{ background: '#f1f5f9', padding: '1px 5px', borderRadius: 3, fontSize: 12, fontFamily: 'monospace' }}>{match[6]}</code>);
      } else if (match[7] !== undefined) {
        parts.push(<del key={key++} style={{ color: '#999' }}>{match[7]}</del>);
      }

      lastIndex = pattern.lastIndex;
    }

    if (lastIndex < remaining.length) {
      parts.push(remaining.slice(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  }

  const lines = content.split('\n');
  const elements = [];
  let inCodeBlock = false;
  let codeLines = [];
  let codeLang = '';
  let inTable = false;
  let tableRows = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // 跳过所有前导 frontmatter 块（可能因编辑bug出现多个）
    if (line === '---' && !inCodeBlock && elements.length === 0 && !inTable) {
      while (i + 1 < lines.length && lines[i + 1] !== '---') i++;
      i++; // 跳过闭合的 ---
      continue;
    }

    // 代码块
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        elements.push(
          <pre key={i} style={{ background: '#1e293b', color: '#e2e8f0', padding: '12px 16px', borderRadius: 8, fontSize: 12, overflow: 'auto', maxHeight: 300, lineHeight: 1.6 }}>
            {codeLang && <div style={{ color: '#94a3b8', fontSize: 11, marginBottom: 4 }}>{codeLang}</div>}
            {codeLines.join('\n')}
          </pre>
        );
        codeLines = [];
        codeLang = '';
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        codeLang = line.slice(3).trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    // 表格处理
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!inTable) {
        inTable = true;
        tableRows = [];
      }
      // 跳过分隔行
      if (line.match(/^\|[\s\-:|]+\|$/)) continue;
      const cells = line.split('|').slice(1, -1).map(c => c.trim());
      tableRows.push(cells);
      continue;
    } else if (inTable) {
      // 表格结束，渲染
      const header = tableRows[0];
      const body = tableRows.slice(1);
      // 合并单元格：空单元格继承上一行的值
      const mergedBody = body.map((row, ri) => {
        const prevRow = ri > 0 ? body[ri - 1] : null;
        return row.map((cell, ci) => {
          if (!cell && prevRow && prevRow[ci]) return prevRow[ci];
          return cell;
        });
      });
      elements.push(
        <div key={`tbl-${i}`} style={{ overflow: 'auto', margin: '8px 0' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            {header && (
              <thead>
                <tr>
                  {header.map((h, j) => (
                    <th key={j} style={{ border: '1px solid #e2e8f0', padding: '6px 10px', background: isDark ? '#252525' : '#f8fafc', textAlign: 'left', fontWeight: 600, color: isDark ? '#bbb' : '#334155', whiteSpace: 'nowrap' }}>{renderInline(h)}</th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {mergedBody.map((row, ri) => (
                <tr key={ri} style={{ background: ri % 2 === 0 ? (isDark ? '#1a1a1a' : '#fff') : (isDark ? '#222' : '#fafafa') }}>
                  {row.map((cell, cj) => (
                    <td key={cj} style={{ border: '1px solid #e2e8f0', padding: '6px 10px', color: '#4B5563', whiteSpace: cj === 0 ? 'nowrap' : 'normal' }}>{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      inTable = false;
      tableRows = [];
    }

    // 空行
    if (!line.trim()) {
      elements.push(<div key={i} style={{ height: 8 }} />);
      continue;
    }

    // 水平线
    if (line.match(/^[-*_]{3,}$/)) {
      elements.push(<hr key={i} style={{ border: 'none', borderTop: '1px solid #e2e8f0', margin: '12px 0' }} />);
      continue;
    }

    // 标题
    if (line.startsWith('#### ')) {
      elements.push(<Text strong key={i} style={{ fontSize: 13, display: 'block', marginTop: 10, marginBottom: 4, color: '#64748B' }}>{renderInline(line.slice(5))}</Text>);
    } else if (line.startsWith('### ')) {
      elements.push(<Text strong key={i} style={{ fontSize: 14, display: 'block', marginTop: 12, marginBottom: 4 }}>{renderInline(line.slice(4))}</Text>);
    } else if (line.startsWith('## ')) {
      elements.push(<Text strong key={i} style={{ fontSize: 15, display: 'block', marginTop: 16, marginBottom: 6, color: '#0D9488' }}>{renderInline(line.slice(3))}</Text>);
    } else if (line.startsWith('# ')) {
      elements.push(<Text strong key={i} style={{ fontSize: 16, display: 'block', marginTop: 16, marginBottom: 8 }}>{renderInline(line.slice(2))}</Text>);
    }
    // 引用
    else if (line.startsWith('> ')) {
      elements.push(
        <div key={i} style={{ borderLeft: '3px solid #0D9488', padding: '4px 12px', margin: '4px 0', background: 'rgba(13,148,136,0.04)', borderRadius: '0 4px 4px 0', color: '#64748B', fontSize: 13 }}>
          {renderInline(line.replace(/^>\s?/, ''))}
        </div>
      );
    }
    // 有序列表
    else if (line.match(/^\d+\.\s/)) {
      const num = line.match(/^(\d+)\./)[1];
      elements.push(
        <div key={i} style={{ paddingLeft: 16, fontSize: 13, lineHeight: 1.8, color: '#4B5563' }}>
          {num}. {renderInline(line.replace(/^\d+\.\s/, ''))}
        </div>
      );
    }
    // 无序列表
    else if (line.match(/^[-*]\s/)) {
      elements.push(
        <div key={i} style={{ paddingLeft: 16, fontSize: 13, lineHeight: 1.8, color: '#4B5563' }}>
          • {renderInline(line.replace(/^[-*]\s/, ''))}
        </div>
      );
    }
    // 普通段落
    else {
      elements.push(
        <Text key={i} style={{ fontSize: 13, display: 'block', lineHeight: 1.8, color: '#4B5563' }}>
          {renderInline(line)}
        </Text>
      );
    }
  }

  // 处理未关闭的表格
  if (inTable && tableRows.length > 0) {
    const header = tableRows[0];
    const body = tableRows.slice(1);
    const mergedBody = body.map((row, ri) => {
      const prevRow = ri > 0 ? body[ri - 1] : null;
      return row.map((cell, ci) => {
        if (!cell && prevRow && prevRow[ci]) return prevRow[ci];
        return cell;
      });
    });
    elements.push(
      <div key="tbl-end" style={{ overflow: 'auto', margin: '8px 0' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          {header && (
            <thead>
              <tr>
                {header.map((h, j) => (
                  <th key={j} style={{ border: '1px solid #e2e8f0', padding: '6px 10px', background: '#f8fafc', textAlign: 'left', fontWeight: 600 }}>{renderInline(h)}</th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {mergedBody.map((row, ri) => (
              <tr key={ri} style={{ background: ri % 2 === 0 ? (isDark ? '#1a1a1a' : '#fff') : (isDark ? '#222' : '#fafafa') }}>
                {row.map((cell, cj) => (
                  <td key={cj} style={{ border: '1px solid #e2e8f0', padding: '6px 10px' }}>{renderInline(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return <div style={{ maxHeight: 'calc(100vh - 200px)', overflow: 'auto' }}>{elements}</div>;
}

export default SimpleMarkdown;