import { useAuth } from '../auth/AuthContext';
import AlertBanner from '../components/AlertBanner';

export default function GuardPage() {
  const { token } = useAuth();

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col">
      <AlertBanner token={token} />

      {/* Header */}
      <div className="bg-gray-800 px-6 py-3 flex items-center justify-between">
        <h1 className="text-white text-lg font-semibold">Live Camera Feed</h1>
        <span className="text-green-400 text-sm flex items-center gap-1">
          <span className="inline-block w-2 h-2 bg-green-400 rounded-full animate-pulse" />
          LIVE
        </span>
      </div>

      {/* Video feed — always point to backend :8000 */}
      <div className="flex-1 flex items-center justify-center p-4">
        <img
          src={`http://localhost:8000/guard/video_feed?token=${token}`}
          alt="Live camera feed"
          style={{ maxWidth: '100%', maxHeight: 'calc(100vh - 120px)', borderRadius: '8px' }}
        />
      </div>
    </div>
  );
}
