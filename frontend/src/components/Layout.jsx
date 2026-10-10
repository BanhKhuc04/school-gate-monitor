import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopStatusBar from './TopStatusBar';
import PageLoading from './PageLoading';

/**
 * Wraps authenticated pages with the left Sidebar nav + top status bar
 * (command-center layout — see stitch_school_gate_monitor_landing_page mockups).
 * Uses <Outlet /> so React Router v6 nested routes can render the matched child.
 */
export default function Layout() {
  return (
    <div className="min-h-screen bg-surface-container-low">
      <Sidebar />
      <div className="md:ml-64 min-w-0 flex flex-col min-h-screen">
        <TopStatusBar />
        <main className="flex-1 min-w-0"><Suspense fallback={<PageLoading />}><Outlet /></Suspense></main>
      </div>
    </div>
  );
}
