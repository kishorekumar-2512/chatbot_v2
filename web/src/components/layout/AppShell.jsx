import useChatStore from '../../stores/chatStore.js';
import useSchema from '../../hooks/useSchema.js';
import useChat from '../../hooks/useChat.js';
import StatusBar from './StatusBar.jsx';
import Sidebar from './Sidebar.jsx';
import OrgLogin from './OrgLogin.jsx';
import ChatPanel from '../chat/ChatPanel.jsx';
import SettingsDrawer from '../settings/SettingsDrawer.jsx';

/**
 * AppShell — root layout. Shows org login gate, then full app with sidebar + chat.
 */
export default function AppShell() {
  const orgId = useChatStore((s) => s.orgId);
  const setOrgId = useChatStore((s) => s.setOrgId);
  const sidebarOpen = useChatStore((s) => s.sidebarOpen);
  const { send } = useChat();

  /* Start health polling */
  useSchema();

  if (!orgId) {
    return <OrgLogin onLogin={setOrgId} />;
  }

  const shellClass = [
    'app-shell',
    !sidebarOpen && 'sidebar-collapsed',
  ].filter(Boolean).join(' ');

  return (
    <div className={shellClass}>
      <Sidebar onSelectQuery={send} />
      <StatusBar />
      <div className="main-content">
        <ChatPanel />
      </div>
      <SettingsDrawer />
    </div>
  );
}
