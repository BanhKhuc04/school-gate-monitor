import Sidebar from './Sidebar';
import TopStatusBar from './TopStatusBar';

/**
 * Wraps authenticated pages with the left Sidebar nav + top status bar
 * (command-center layout — see stitch_school_gate_monitor_landing_page mockups).
 */
export default function Layout({ children }) {
  return (
    <div className="min-h-screen bg-surface-container-low">
      <Sidebar />
      <div className="ml-64 flex flex-col min-h-screen">
        <TopStatusBar />
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
