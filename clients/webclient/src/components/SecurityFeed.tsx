import React from 'react';
import { Button } from '@/components/ui/button';

type SecurityFeedProps = {
  count: number;
  onOpen: () => void;
};

export const SecurityFeed: React.FC<SecurityFeedProps> = ({ count, onOpen }) => {
  if (count <= 0) return null;

  const label = count === 1 ? '1 notification pending' : `${count} notifications pending`;

  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-[120]">
      <div className="pointer-events-auto">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="ui-security-feed-btn border backdrop-blur-sm"
          onClick={onOpen}
        >
          {label}
        </Button>
      </div>
    </div>
  );
};
