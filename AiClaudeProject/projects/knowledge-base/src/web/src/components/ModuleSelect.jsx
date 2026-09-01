/**
 * ModuleSelect.jsx - 模块模糊搜索选择器
 *
 * 从 /api/menu 的 moduleOptions 获取模块（含唯一 ID），支持模糊搜索匹配。
 * onChange(name, moduleId)：选择已有模块时携带 ID，输入自定义名称时 ID 为 0。
 */
import React, { useState, useEffect } from 'react';
import { authFetch } from '../api';
import { AutoComplete } from 'antd';

// 全局缓存，避免重复请求
let cachedModuleOptions = null;

function ModuleSelect({ value, onChange, placeholder = '输入模块名搜索...', style, ...rest }) {
  const [options, setOptions] = useState(() => cachedModuleOptions || []);

  useEffect(() => {
    if (cachedModuleOptions) {
      setOptions(cachedModuleOptions);
      return;
    }
    authFetch('/api/menu')
      .then(r => r.json())
      .then(data => {
        const opts = (data.moduleOptions || []).map(m => ({
          value: m.name, label: m.name, moduleId: m.id,
        }));
        cachedModuleOptions = opts;
        setOptions(opts);
      })
      .catch(() => setOptions([]));
  }, []);

  return (
    <AutoComplete
      value={value}
      onChange={(v) => {
        const opt = options.find(o => o.value === v);
        onChange(v, opt ? opt.moduleId : 0);
      }}
      options={options}
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