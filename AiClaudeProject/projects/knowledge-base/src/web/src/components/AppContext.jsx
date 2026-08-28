/**
 * AppContext.jsx - 应用全局状态 Context
 *
 * 替代 props drilling，提供 isDark、selectedDoc、searchResults 等共享状态。
 * 子组件通过 useContext(AppContext) 直接获取，无需层层传递 props。
 */
import React, { createContext, useContext } from 'react';

const AppContext = createContext(null);

/** Provider 组件，包裹在 App 顶层 */
function AppProvider({ children, value }) {
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

/** Hook: 获取全局状态 */
function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext 必须在 AppProvider 内使用');
  return ctx;
}

export { AppContext, AppProvider, useAppContext };
export default AppContext;