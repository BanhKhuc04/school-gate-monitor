import NavBar from './NavBar';

/**
 * Wraps authenticated pages with NavBar.
 */
export default function Layout({ children }) {
  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      <NavBar />
      <main className="flex-1">{children}</main>
    </div>
  );
}
