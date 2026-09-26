import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';

/**
 * Client-side route guard. Redirects to /login if not authenticated,
 * or to the user's default page if their role is not in the `allow` list.
 * Real enforcement is always done on the server.
 */
export default function RequireRole({ allow = [], children }) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!allow.includes(user.role)) {
    // Redirect each role to their default page
    const defaults = {
      admin: '/admin/vehicles',
      security: '/guard',
      management: '/dashboard',
    };
    return <Navigate to={defaults[user.role] || '/login'} replace />;
  }

  return children;
}
