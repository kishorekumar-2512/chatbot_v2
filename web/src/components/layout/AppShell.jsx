import React, { useEffect } from 'react';
import useChatStore from '../../stores/chatStore.js';
import useSchema from '../../hooks/useSchema.js';
import useChat from '../../hooks/useChat.js';
import TopNav from './TopNav.jsx';
import Sidebar from './Sidebar.jsx';
import RightSidebar from './RightSidebar.jsx';
import OrgLogin from './OrgLogin.jsx';
import ChatPanel from '../chat/ChatPanel.jsx';
import HomeDashboard from '../chat/HomeDashboard.jsx';
import SettingsDrawer from '../settings/SettingsDrawer.jsx';
import ToastStack from './ToastStack.jsx';

/**
 * AppShell — root layout. Shows org login gate, then full app with sidebar + chat.
 */
export default function AppShell() {
  const orgId = useChatStore((s) => s.orgId);
  const setOrgId = useChatStore((s) => s.setOrgId);
  const sidebarOpen = useChatStore((s) => s.sidebarOpen);
  const setSidebarOpen = useChatStore((s) => s.setSidebarOpen);
  const rightSidebarOpen = useChatStore((s) => s.rightSidebarOpen);
  const setRightSidebarOpen = useChatStore((s) => s.setRightSidebarOpen);
  const messages = useChatStore((s) => s.messages);
  const { send } = useChat();

  /* Start health polling */
  useSchema();

  /* Listen to screen width changes and adjust sidebars recursively to protect layout flow */
  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth;
      if (width < 1024) {
        setSidebarOpen(false);
      } else {
        setSidebarOpen(true);
      }
      
      if (width < 1400) {
        setRightSidebarOpen(false);
      } else {
        setRightSidebarOpen(true);
      }
    };

    handleResize(); // Run immediately on mount
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [setSidebarOpen, setRightSidebarOpen]);

  if (!orgId) {
    return <OrgLogin onLogin={setOrgId} />;
  }

  const shellClass = [
    'app-shell',
    !sidebarOpen && 'sidebar-collapsed',
    rightSidebarOpen ? 'right-sidebar-expanded' : 'right-sidebar-collapsed'
  ].filter(Boolean).join(' ');

  return (
    <div className={shellClass}>
      <Sidebar onSelectQuery={send} />
      <TopNav />
      <div className="main-content">
        <ChatPanel />
      </div>
      <RightSidebar onSelectQuery={send} />
      <SettingsDrawer />
      <ToastStack />
    </div>
  );
}
