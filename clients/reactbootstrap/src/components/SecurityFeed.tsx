import React from 'react';
import { Button } from 'design-react-kit';

type SecurityFeedProps = {
  count: number;
  onOpen: () => void;
};

export const SecurityFeed: React.FC<SecurityFeedProps> = ({ count, onOpen }) => {
  if (count <= 0) return null;

  const label = count === 1 ? '1 notifica pendente' : `${count} notifiche pendenti`;

  return (
    <div className="position-fixed end-0 bottom-0 p-3" style={{ zIndex: 120, pointerEvents: 'none' }}>
      <div style={{ pointerEvents: 'auto' }}>
        <Button
          type="button"
          size="sm"
          color="secondary"
          className="ui-security-feed-btn border shadow-sm"
          onClick={onOpen}
        >
          {label}
        </Button>
      </div>
    </div>
  );
};
