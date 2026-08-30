/**
 * DeptCascader.jsx - 级联部门选择器
 *
 * 从数据库部门树动态加载，支持三级级联选择和多选。
 * 用于文档上传、FAQ编辑等需要选择部门的场景。
 *
 * Props:
 *   value       - 选中的部门ID数组，如 [1062036871] 或 [986881778, 1062036871]
 *   onChange    - (deptIds, deptNames, deptPaths) => void
 *   multiple    - 是否多选，默认 false
 *   placeholder - 占位文本
 *   style       - 额外样式
 */
import React, { useState, useEffect, useMemo } from 'react';
import { authFetch } from '../api';
import { Cascader } from 'antd';

/** 将部门树转为 Cascader 需要的 options 格式 */
function treeToOptions(tree) {
  if (!tree || tree.length === 0) return [];
  return tree.map(node => ({
    value: node.id,
    label: `${node.name} (${node.doc_count || 0})`,
    children: node.children?.length > 0 ? treeToOptions(node.children) : undefined,
  }));
}

function DeptCascader({ value, onChange, multiple = false, placeholder = '请选择部门', style = {} }) {
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authFetch('/api/departments/tree')
      .then(r => r.json())
      .then(data => {
        setOptions(treeToOptions(data?.tree || []));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // 将 value (ID数组) 转为 Cascader 需要的路径数组
  // 例如 value=[1062036871] → [[590477194, 986881778, 1062036871]]
  const cascaderValue = useMemo(() => {
    if (!value || value.length === 0) return multiple ? [] : undefined;
    // 构建 ID→节点 的映射，便于查找路径
    const idMap = {};
    function buildMap(nodes) {
      for (const n of nodes) {
        idMap[n.value] = n;
        if (n.children) buildMap(n.children);
      }
    }
    buildMap(options);

    const paths = [];
    for (const id of value) {
      // 在树中查找该ID的完整路径
      function findPath(nodes, target, currentPath = []) {
        for (const n of nodes) {
          const newPath = [...currentPath, n.value];
          if (n.value === target) return newPath;
          if (n.children) {
            const found = findPath(n.children, target, newPath);
            if (found) return found;
          }
        }
        return null;
      }
      const path = findPath(options, id);
      if (path) paths.push(path);
    }
    return multiple ? paths : (paths[0] || undefined);
  }, [value, options, multiple]);

  const handleChange = (cascaderValues) => {
    if (!cascaderValues || cascaderValues.length === 0) {
      onChange([], [], []);
      return;
    }

    const vals = multiple ? cascaderValues : [cascaderValues];
    const deptIds = [];
    const deptNames = [];
    const deptPaths = [];

    // 构建 ID→名称 映射
    const idToName = {};
    function mapNames(nodes, parentPath = '') {
      for (const n of nodes) {
        const path = parentPath ? `${parentPath} > ${n.label.split(' (')[0]}` : n.label.split(' (')[0];
        idToName[n.value] = { name: n.label.split(' (')[0], path };
        if (n.children) mapNames(n.children, path);
      }
    }
    mapNames(options);

    for (const valPath of vals) {
      const lastId = valPath[valPath.length - 1]; // 取最后一级的ID
      if (idToName[lastId]) {
        deptIds.push(lastId);
        deptNames.push(idToName[lastId].name);
        deptPaths.push(idToName[lastId].path);
      }
    }

    onChange(deptIds, deptNames, deptPaths);
  };

  return (
    <Cascader
      options={options}
      value={cascaderValue}
      onChange={handleChange}
      multiple={multiple}
      placeholder={placeholder}
      loading={loading}
      style={{ width: '100%', ...style }}
      showSearch
      maxTagCount={multiple ? 3 : undefined}
      maxTagPlaceholder={(omitted) => `+${omitted.length} 个部门`}
    />
  );
}

export default DeptCascader;
export { treeToOptions };