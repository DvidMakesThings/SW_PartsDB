import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Database, Layers, Upload, Paperclip, Settings, ExternalLink } from 'lucide-react';
import { cn } from '../../lib/utils';

interface NavItemProps {
  to: string;
  icon: React.ReactNode;
  label: string;
  isActive: boolean;
  isExternal?: boolean;
}

const NavItem: React.FC<NavItemProps> = ({ to, icon, label, isActive, isExternal }) => {
  if (isExternal) {
    return (
      <a
        href={to}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors",
          "hover:bg-[var(--surface)] hover:text-[var(--accent)]"
        )}
      >
        {icon}
        <span>{label}</span>
        <ExternalLink className="h-3 w-3 opacity-70" />
      </a>
    );
  }
  
  return (
    <Link
      to={to}
      className={cn(
        "flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors",
        isActive 
          ? "bg-[var(--surface)] text-[var(--accent)]" 
          : "hover:bg-[var(--surface)] hover:text-[var(--accent)]"
      )}
    >
      {icon}
      <span>{label}</span>
    </Link>
  );
};

const Navbar: React.FC = () => {
  const location = useLocation();
  const currentPath = location.pathname;

  const navItems = [
    {
      to: '/',
      icon: <Database className="h-4 w-4" />,
      label: 'Components'
    },
    {
      to: '/inventory',
      icon: <Layers className="h-4 w-4" />,
      label: 'Inventory'
    },
    {
      to: '/import',
      icon: <Upload className="h-4 w-4" />,
      label: 'Import CSV'
    },
    {
      to: '/attachments',
      icon: <Paperclip className="h-4 w-4" />,
      label: 'Attachments'
    }
  ];

  return (
    <nav className="bg-[var(--surface)] border-b border-[var(--border)] px-4 py-2">
      <div className="flex justify-between items-center">
        <div className="flex items-center">
          <h1 className="text-lg font-semibold mr-6 text-[var(--accent)]">PartsDB</h1>
          <div className="flex items-center space-x-1">
            {navItems.map((item) => (
              <NavItem
                key={item.to}
                to={item.to}
                icon={item.icon}
                label={item.label}
                isActive={
                  currentPath === item.to ||
                  (item.to !== '/' && currentPath.startsWith(item.to))
                }
              />
            ))}
          </div>
        </div>
        
        <NavItem
          to="/admin"
          icon={<Settings className="h-4 w-4" />}
          label="Admin"
          isActive={false}
          isExternal={true}
        />
      </div>
    </nav>
  );
};

export default Navbar;