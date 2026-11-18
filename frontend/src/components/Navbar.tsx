import React from 'react';
import { DASHBOARD_PATHS, DashboardPage, PAGE_TITLES } from '../types/trading';

type NavbarProps = {
  currentPage: DashboardPage;
  onNavigate: (page: DashboardPage) => void;
};

const NAV_ITEMS: DashboardPage[] = ['account', 'market', 'trade-bot', 'pnl-hedge'];

export default function Navbar({ currentPage, onNavigate }: NavbarProps) {
  function handleClick(e: React.MouseEvent<HTMLAnchorElement>, page: DashboardPage) {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    onNavigate(page);
  }

  return (
    <nav className="dashboardSubnav" aria-label="Main navigation">
      {NAV_ITEMS.map((page) => {
        const href = DASHBOARD_PATHS[page];
        const isActive = currentPage === page;
        return (
          <a
            key={page}
            href={href}
            aria-current={isActive ? 'page' : undefined}
            className={isActive ? 'activeNavLink' : ''}
            onClick={(e) => handleClick(e, page)}
          >
            {PAGE_TITLES[page]}
          </a>
        );
      })}
    </nav>
  );
}
