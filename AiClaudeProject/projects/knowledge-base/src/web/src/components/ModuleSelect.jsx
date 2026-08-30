/**
 * ModuleSelect.jsx - 模块模糊搜索选择器
 *
 * 从 /api/menu 获取所有可用模块名，支持模糊搜索匹配
 * 允许输入自定义值，也支持从下拉列表中选择
 */
import React, { useState, useEffect } from 'react';
import { authFetch } from '../api';
import { AutoComplete } from 'antd';

/** 从 menu API 数据中提取所有模块名 */
function extractModules(menuData) {
  const modules = new Set();
  if (!menuData) return [];

  // 产品模块
  const productModules = menuData.productModules || {};
  for (const line of Object.values(productModules)) {
    for (const mods of Object.values(line)) {
      for (const m of mods) {
        const name = typeof m === 'string' ? m : m?.name;
        if (name) modules.add(name);
      }
    }
  }

  // 业务模块
  const businessModules = menuData.businessModules || {};
  for (const lines of Object.values(businessModules)) {
    for (const prods of Object.values(lines)) {
      for (const mods of Object.values(prods)) {
        for (const m of mods) {
          if (typeof m === 'string') modules.add(m);
        }
      }
    }
  }

  return [...modules].sort();
}

// 全局缓存，避免重复请求
let cachedModules = null;

function ModuleSelect({ value, onChange, placeholder = '输入模块名搜索...', style, ...rest }) {
  const [options, setOptions] = useState(() => cachedModules || []);

  useEffect(() => {
    if (cachedModules) {
      setOptions(cachedModules);
      return;
    }
    authFetch('/api/menu')
      .then(r => r.json())
      .then(data => {
        const mods = extractModules(data);
        cachedModules = mods;
        setOptions(mods);
      })
      .catch(() => setOptions([]));
  }, []);

  return (
    <AutoComplete
      value={value}
      onChange={onChange}
      options={options.map(m => ({ value: m, label: m }))}
      placeholder={placeholder}
      filterOption={(inputValue, option) =>
        option.value.toLowerCase().includes(inputValue.toLowerCase())
      }
      style={{ width: '100%', ...style }}
      allowClear
      {...rest}
    />
  );
}

export default ModuleSelect;