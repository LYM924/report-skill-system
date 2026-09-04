/**
 * AdminShell.jsx - 管理页统一布局
 *
 * 提供一致的标题栏、描述、错误边界包裹。
 * 管理模块组件只需关心自身内容，不再各自写标题/样式。
 */

import React from 'react';
import { Typography, Result, Button } from 'antd';
import { useAppContext } from '../AppContext';

const { Text } = Typography;

class AdminErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title="模块加载失败"
          subTitle={this.state.error?.message || '请刷新页面重试'}
          extra={
            <Button type="primary" onClick={() => this.setState({ hasError: false, error: null })}>
              重试
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}

/**
 * 管理页外壳组件
 *
 * @param {string} title - 页面标题
 * @param {string} [description] - 页面描述（可选）
 * @param {ReactNode} [extra] - 标题栏右侧额外内容（如操作按钮）
 * @param {ReactNode} children - 页面内容
 */
function AdminShell({ title, description, extra, children }) {
  const { isDark } = useAppContext();

  return (
    <div style={{ width: '100%', maxWidth: 960 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: description ? 4 : 20 }}>
        <Text strong style={{ fontSize: 20, color: isDark ? '#e5e5e5' : '#1e293b' }}>
          {title}
        </Text>
        {extra}
      </div>
      {description && (
        <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 16 }}>
          {description}
        </Text>
      )}
      <AdminErrorBoundary>
        {children}
      </AdminErrorBoundary>
    </div>
  );
}

export default AdminShell;
