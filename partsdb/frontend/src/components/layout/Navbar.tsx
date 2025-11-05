import { Link, useLocation } from 'react-router-dom';
import { Database, Package, Upload, Settings, ExternalLink, Sun, Moon } from 'lucide-react';
import { useState, useEffect } from 'react';

const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || '';

export default function Navbar() {
  const location = useLocation();
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');

  useEffect(() => {
    // Load theme from localStorage on mount
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' | null;
    if (savedTheme) {
      setTheme(savedTheme);
      document.documentElement.setAttribute('data-theme', savedTheme);
    } else {
      // Check system preference
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const defaultTheme = prefersDark ? 'dark' : 'light';
      setTheme(defaultTheme);
      document.documentElement.setAttribute('data-theme', defaultTheme);
    }
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
  };

  const navItems = [
    { path: '/components', label: 'Components', icon: Database },
    { path: '/inventory', label: 'Inventory', icon: Package },
    { path: '/import', label: 'Import', icon: Upload },
  ];

  const isActive = (path: string) => location.pathname.startsWith(path);

  return (
    <nav className="sticky top-0 z-50 bg-[--surface] border-b border-[--border] backdrop-blur-sm bg-opacity-90">
      <div className="container mx-auto px-4 max-w-7xl">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 group">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center">
              <Database className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold gradient-text">PartsDB</span>
          </Link>

          {/* Navigation Links */}
          <div className="flex items-center gap-1">
            {navItems.map(({ path, label, icon: Icon }) => (
              <Link
                key={path}
                to={path}
                className={`
                  flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm
                  transition-all duration-150
                  ${isActive(path)
                    ? 'bg-[--accent] text-white shadow-lg shadow-blue-500/20'
                    : 'text-[--text-secondary] hover:text-[--text] hover:bg-[--surface-hover]'
                  }
                `}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            ))}

            {/* Theme Toggle */}
            <button
              onClick={toggleTheme}
              className="flex items-center gap-2 px-3 py-2 rounded-lg font-medium text-sm text-[--text-secondary] hover:text-[--text] hover:bg-[--surface-hover] transition-all duration-150 ml-2 group"
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              {theme === 'dark' ? (
                <Sun className="w-4 h-4 group-hover:rotate-180 transition-transform duration-300" />
              ) : (
                <Moon className="w-4 h-4 group-hover:-rotate-12 transition-transform duration-300" />
              )}
            </button>

            {/* Admin Link */}
            <a
              href={`${BACKEND_ORIGIN}/admin/`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm text-[--text-secondary] hover:text-[--text] hover:bg-[--surface-hover] transition-all duration-150"
            >
              <Settings className="w-4 h-4" />
              Admin
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </div>
    </nav>
  );
}
