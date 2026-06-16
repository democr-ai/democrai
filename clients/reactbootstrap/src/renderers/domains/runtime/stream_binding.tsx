import React from 'react';

export const StreamBinding: React.FC<{
  id?: string;
  stream?: string;
  event?: string;
  target?: any;
  transformer?: any;
  sendAction?: (name: string, context?: any, surfaceId?: string, componentId?: string) => void;
  surfaceId?: string;
}> = ({ id, stream, event, target, transformer, sendAction, surfaceId }) => {
  const targetKey = JSON.stringify(target || {});
  const transformerKey = JSON.stringify(transformer || {});

  React.useEffect(() => {
    const bindingId = String(id || '').trim();
    const sourceStream = String(stream || '').trim();
    const parsedTarget = JSON.parse(targetKey || '{}');
    const parsedTransformer = JSON.parse(transformerKey || '{}');
    if (!bindingId || !sourceStream || !parsedTarget || typeof sendAction !== 'function') {
      return;
    }
    sendAction(
      '__stream_binding.subscribe',
      {
        bindingId,
        stream: sourceStream,
        event: String(event || '').trim(),
        target: parsedTarget,
        transformer: parsedTransformer,
      },
      surfaceId || 'main',
      bindingId,
    );
    return () => {
      sendAction(
        '__stream_binding.unsubscribe',
        { bindingId },
        surfaceId || 'main',
        bindingId,
      );
    };
  }, [id, stream, event, targetKey, transformerKey, sendAction, surfaceId]);

  return null;
};
