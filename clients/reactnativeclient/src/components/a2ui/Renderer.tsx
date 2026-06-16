import React from 'react';
import { View, Text, StyleSheet, ActivityIndicator, Dimensions } from 'react-native';
import { Registry } from '../../renderers/index';
import { 
  evaluateRule, 
  resolveActiveValue, 
  resolveBindings, 
  isObject,
} from '../../renderers/rules';
import { parseStyle } from '../../utils/style';
import { clampResponsiveStyle } from '../../utils/responsive';

type RendererProps = {
  surfaceId: string;
  componentId: string;
  surfaces: any;
  dataModel: any;
  stateModel: any;
  sendAction: any;
  setInput: any;
  userRole: string;
  userPermissions: string[];
  pendingActions?: Record<string, number>;
  backgroundTasks?: Record<string, any>;
  jwt?: string;
  item?: Record<string, any>;
  centerRootContent?: boolean;
  preserveRootStretch?: boolean;
  naturalRoot?: boolean;
  insideNaturalScroll?: boolean;
};

const getByPath = (obj: any, path: string): any => {
  if (!obj || !path) return obj;
  return String(path).replace(/^\//, '').split(/[./]/).filter(Boolean).reduce((acc, segment) => {
    if (acc == null || typeof acc !== 'object') return undefined;
    return acc[segment];
  }, obj);
};

const normalizePermissions = (value: unknown): string[] => {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => String(entry)).filter(Boolean);
};

const isSuperRole = (role: string): boolean => {
  const normalized = String(role || '').trim().toLowerCase();
  return normalized === 'super' || normalized === 'admin';
};

const readStateValue = (stateModel: any, scope: 'global' | 'page' | 'auto', path: string): any => {
  if (scope === 'page') return getByPath(stateModel?.page, path);
  if (scope === 'global') {
    const fromGlobal = getByPath(stateModel?.global, path);
    return fromGlobal !== undefined ? fromGlobal : getByPath(stateModel, path);
  }
  const fromPage = getByPath(stateModel?.page, path);
  if (fromPage !== undefined) return fromPage;
  const fromGlobal = getByPath(stateModel?.global, path);
  if (fromGlobal !== undefined) return fromGlobal;
  return getByPath(stateModel, path);
};

const resolveAccessContext = (stateModel: any, role: string, permissions: string[]) => {
  const storeRoleValue = readStateValue(stateModel, 'global', '/auth/role');
  const storeRole = typeof storeRoleValue === 'string' ? storeRoleValue : '';
  const storePermissions = normalizePermissions(readStateValue(stateModel, 'global', '/auth/permissions'));
  const permissionsLoaded = readStateValue(stateModel, 'global', '/auth/permissions_loaded') === true;
  const shouldUseStore = permissionsLoaded || storePermissions.length > 0 || Boolean(storeRole && storeRole.toLowerCase() !== 'guest');

  return {
    role: shouldUseStore ? (storeRole || role || 'Guest') : (role || 'Guest'),
    permissions: shouldUseStore ? storePermissions : normalizePermissions(permissions),
  };
};

const hasAccess = (requiredPerms: string[] | string | undefined, role: string, permissions: string[]): boolean => {
  const required = Array.isArray(requiredPerms) ? requiredPerms : requiredPerms ? [requiredPerms] : [];
  if (required.length === 0) return true;
  if (isSuperRole(role)) return true;
  return required.some((perm) => permissions.includes(perm));
};

// Layout container types whose wrapper gains flex:1 when stretch=true.
// Leaf/form types (TextField, Button, etc.) are intentionally excluded so
// that stretch on a form control only affects the component's own view, not
// its wrapper.
const FLEX_FILL_TYPES = new Set(['Column', 'Row', 'FlexContainer', 'Card', 'ScrollArea', 'ContentArea', 'Splitter', 'Tabs', 'MessageList']);
const NATURAL_FLOW_TYPES = new Set(['Column', 'Row', 'FlexContainer', 'Card', 'ScrollArea', 'ContentArea', 'Splitter', 'Tabs']);

export const InternalRenderer: React.FC<{
  componentData: any;
  surfaceId: string;
  surfaces: any;
  dataModel: any;
  stateModel: any;
  sendAction: any;
  setInput: any;
  componentId: string;
  userRole: string;
  userPermissions: string[];
  pendingActions?: Record<string, number>;
  backgroundTasks?: Record<string, any>;
  jwt?: string;
  item?: Record<string, any>;
  isRoot?: boolean;
  insideNaturalScroll?: boolean;
}> = ({
  componentData,
  surfaceId,
  surfaces,
  dataModel,
  stateModel,
  sendAction,
  setInput,
  componentId,
  userRole,
  userPermissions,
  pendingActions,
  backgroundTasks,
  jwt,
  item,
  isRoot,
  insideNaturalScroll,
}) => {
  if (!componentData || !componentData.component) return null;

  try {
    const type = Object.keys(componentData.component)[0];
    const rawProps = componentData.component[type] || {};
    const requiredPermissions = rawProps.required_permissions
      ?? rawProps.permissions
      ?? rawProps.check_permission
      ?? rawProps.check_permissions
      ?? componentData.required_permissions
      ?? componentData.check_permission
      ?? componentData.check_permissions
      ?? componentData.permissions;
    const access = resolveAccessContext(stateModel, userRole, userPermissions);

    if (!hasAccess(requiredPermissions, access.role, access.permissions)) {
      return null;
    }

    const surfaceModel = dataModel?.[surfaceId] || {};

    console.log(`[A2UI] Encountered ${type} (${componentId}) on ${surfaceId}`);

    const options = {
      surfaceModel,
      stateModel,
      item,
      formValues: surfaceModel,
    };

    // Visibility checks (show_if / hide_if)
    const showIf = rawProps.show_if ?? componentData.show_if;
    const hideIf = rawProps.hide_if ?? componentData.hide_if;

    if (showIf !== undefined && !evaluateRule(showIf, options, true)) {
      console.log(`[A2UI] Skipping ${type} (${componentId}) due to show_if`);
      return null;
    }
    if (hideIf !== undefined && evaluateRule(hideIf, options, false)) {
      console.log(`[A2UI] Skipping ${type} (${componentId}) due to hide_if`);
      return null;
    }

    const props = resolveBindings(rawProps, options);
    if (rawProps && Object.prototype.hasOwnProperty.call(rawProps, 'active')) {
      props.active = resolveActiveValue(rawProps.active, options);
    }
    if (props.style) {
      props.style = parseStyle(props.style);
    }

    if (props.action) {
      console.log(`[A2UI] Component ${componentId} action resolved:`, props.action);
    }

    const ComponentImpl = Registry[type];
    
    if (type === 'SurfaceHost') {
      const hostedSurfaceId = typeof props.surface_id === 'string' ? props.surface_id : (typeof props.surfaceId === 'string' ? props.surfaceId : '');
      const hostedSurface = hostedSurfaceId ? surfaces?.[hostedSurfaceId] : null;
      const hostedRootId = hostedSurface?.rootId || (hostedSurface?.components?.root ? 'root' : '');

      return (
        <View style={{ flex: 1, width: '100%' }}>
          {hostedSurfaceId ? (
            <A2UIRenderer
              surfaceId={hostedSurfaceId}
              componentId={hostedRootId}
              surfaces={surfaces}
              dataModel={dataModel}
              stateModel={stateModel}
              sendAction={sendAction}
              setInput={setInput}
              userRole={userRole}
              userPermissions={userPermissions}
            pendingActions={pendingActions}
            backgroundTasks={backgroundTasks}
            jwt={jwt}
            item={item}
            insideNaturalScroll={insideNaturalScroll}
          />
          ) : (
            <View style={styles.loading}>
              <Text style={styles.muted}>SurfaceHost: Missing surface_id</Text>
            </View>
          )}
        </View>
      );
    }

    const childrenNode = componentData.children || props.children;

    const renderComponentReference = (
      child: any,
      index: number,
      keyPrefix: string,
    ): React.ReactNode => {
      if (isObject(child) && child.component) {
        return (
          <InternalRenderer
            key={child.id || `${keyPrefix}_inline_${index}`}
            componentData={child}
            surfaceId={surfaceId}
            surfaces={surfaces}
            dataModel={dataModel}
            stateModel={stateModel}
            sendAction={sendAction}
            setInput={setInput}
            componentId={child.id || `${keyPrefix}_inline_${index}`}
            userRole={userRole}
            userPermissions={userPermissions}
            pendingActions={pendingActions}
            backgroundTasks={backgroundTasks}
            jwt={jwt}
            item={item}
            insideNaturalScroll={insideNaturalScroll}
          />
        );
      }
      // Look up the child component directly in the surface and render via
      // InternalRenderer — NOT A2UIRenderer — so it does not receive isRoot or
      // the stretch:true patch that is reserved for surface-root components.
      const childId = String(child);
      const childData = surfaces[surfaceId]?.components?.[childId];
      if (!childData) return null;
      return (
        <InternalRenderer
          key={`${keyPrefix}_${childId}`}
          componentData={childData}
          surfaceId={surfaceId}
          surfaces={surfaces}
          dataModel={dataModel}
          stateModel={stateModel}
          sendAction={sendAction}
          setInput={setInput}
          componentId={childId}
          userRole={userRole}
          userPermissions={userPermissions}
          pendingActions={pendingActions}
          backgroundTasks={backgroundTasks}
          jwt={jwt}
          item={item}
          insideNaturalScroll={insideNaturalScroll}
        />
      );
    };

    const buildReferenceList = (items: any, keyPrefix: string): React.ReactNode[] | null => {
      if (!Array.isArray(items) || items.length === 0) {
        return null;
      }
      return items.map((child, index) => renderComponentReference(child, index, keyPrefix));
    };

    const explicitList = buildReferenceList(childrenNode?.explicitList, 'children');
    const hasHeaderSlots =
      Array.isArray(props.left) ||
      Array.isArray(props.center) ||
      Array.isArray(props.right);

    const headerSlotProps = type === 'Header'
      ? {
          leftExplicitList: buildReferenceList(props.left, 'header_left'),
          centerExplicitList: buildReferenceList(
            hasHeaderSlots ? props.center : childrenNode?.explicitList,
            'header_center',
          ),
          rightExplicitList: buildReferenceList(props.right, 'header_right'),
        }
      : {};

    const screenWidth = Dimensions.get('window').width;
    const isPhoneWidth = screenWidth < 700;
    if (isPhoneWidth && type === 'FlexContainer' && React.Children.count(explicitList) === 0) {
      return null;
    }

    // The root surface component always fills available space.
    // Layout containers (Column, Row, FlexContainer…) fill when stretch=true.
    // Leaf/form components never force their wrapper to flex, even with stretch=true.
    const alignVal = String(props.align || '').toLowerCase();
    const naturalFlow = Boolean(insideNaturalScroll && NATURAL_FLOW_TYPES.has(type));
    const needsFlex =
      !naturalFlow && (
      isRoot ||
        componentId === 'content_area_container' ||
        componentId === 'module_root' ||
        componentId === 'comp_list_container' ||
        (!insideNaturalScroll && alignVal === 'fill') ||
        (props.stretch === true && FLEX_FILL_TYPES.has(type)) ||
      type === 'FlexContainer' ||
      type === 'ScrollArea' ||
      type === 'ContentArea' ||
      type === 'Splitter' ||
      type === 'Tabs' ||
      type === 'TreeView' ||
      type === 'SurfaceHost' ||
        type === 'MessageList' ||
        type === 'main'
      );

    const shouldFitParentOnPhone = isPhoneWidth && [
      'Alert',
      'Badge',
      'Button',
      'Card',
      'DataTable',
      'Markdown',
      'Text',
      'Title',
    ].includes(type);

    const wrapperStyle: any = { width: '100%' };
    if (needsFlex) {
      wrapperStyle.flex = 1;
      wrapperStyle.minHeight = 0;
    }

    if (props.style) {
      if (props.style.flex !== undefined) wrapperStyle.flex = props.style.flex;
      if (props.style.width !== undefined && !shouldFitParentOnPhone) wrapperStyle.width = props.style.width;
      if (props.style.height !== undefined) wrapperStyle.height = props.style.height;
      if (props.style.minHeight !== undefined) wrapperStyle.minHeight = props.style.minHeight;
      if (props.style.maxHeight !== undefined) wrapperStyle.maxHeight = props.style.maxHeight;
      if (props.style.flexGrow !== undefined) wrapperStyle.flexGrow = props.style.flexGrow;
      if (props.style.flexShrink !== undefined) wrapperStyle.flexShrink = props.style.flexShrink;
    }
    if (isPhoneWidth) {
      delete wrapperStyle.flex;
      if (typeof wrapperStyle.flexBasis === 'string' || typeof wrapperStyle.flexBasis === 'number') delete wrapperStyle.flexBasis;
      delete wrapperStyle.flexGrow;
      delete wrapperStyle.flexShrink;
      if (needsFlex) {
        wrapperStyle.flex = 1;
        wrapperStyle.minHeight = 0;
      }
      if (typeof props.width === 'number') {
        const maxPhoneWidth = Math.max(0, screenWidth - 48);
        if (!insideNaturalScroll && props.width <= maxPhoneWidth) {
          wrapperStyle.width = props.width;
          wrapperStyle.alignSelf = 'center';
        } else {
          wrapperStyle.width = '100%';
        }
        wrapperStyle.minWidth = 0;
        wrapperStyle.maxWidth = '100%';
      } else if (typeof props.min_width === 'number' || typeof props.minWidth === 'number') {
        wrapperStyle.width = '100%';
        wrapperStyle.minWidth = 0;
        wrapperStyle.maxWidth = '100%';
      }
    }
    if (shouldFitParentOnPhone) {
      wrapperStyle.maxWidth = '100%';
      wrapperStyle.minWidth = 0;
      wrapperStyle.flexShrink = 1;
    }
    const responsiveWrapperStyle = clampResponsiveStyle(wrapperStyle, screenWidth, { inset: 24 });

    return (
      <View style={responsiveWrapperStyle}>
        {ComponentImpl ? (
          <ComponentImpl
            {...(naturalFlow ? { ...props, stretch: false } : props)}
            {...headerSlotProps}
            id={componentId}
            ExplicitList={explicitList}
            onAction={(name: string, ctx: any) => {
              console.log(`[A2UI] Triggering action ${name} with context:`, ctx);
              sendAction(name, ctx, surfaceId, componentId);
            }}
            setInput={setInput}
            surfaces={surfaces}
            dataModel={dataModel}
            stateModel={stateModel}
            sendAction={sendAction}
            surfaceId={surfaceId}
            userRole={userRole}
            userPermissions={userPermissions}
            pendingActions={pendingActions}
            backgroundTasks={backgroundTasks}
            jwt={jwt}
            item={item}
            insideNaturalScroll={insideNaturalScroll}
          />
        ) : (
          <Text style={{ color: '#FF7B72', fontSize: 12 }}>MISSING COMPONENT: {type}</Text>
        )}
      </View>
    );
  } catch (err) {
    console.error(`[A2UI] Error rendering ${componentId}:`, err);
    return (
      <View style={styles.unknown}>
        <Text style={{ color: '#FF7B72', fontSize: 12 }}>Error rendering {componentId}</Text>
      </View>
    );
  }
};

export const A2UIRenderer: React.FC<RendererProps> = (props) => {
  const {
    surfaceId,
    componentId,
    surfaces,
    dataModel,
    stateModel,
    sendAction,
    setInput,
    userRole,
    userPermissions,
    pendingActions,
    backgroundTasks,
    jwt,
    item,
    centerRootContent,
    preserveRootStretch,
    naturalRoot,
    insideNaturalScroll,
  } = props;
  
  const surface = surfaces[surfaceId];
  if (!surface) return null;

  const resolvedComponentId =
    componentId 
      ? (surface.components?.[componentId] ? componentId : '')
      : (surface.rootId || (surface.components?.root ? 'root' : Object.keys(surface.components || {})[0] || ''));

  const componentData = resolvedComponentId ? surface.components[resolvedComponentId] : null;

  if (!componentData) return null;

  // Ensure the root component's own view fills the wrapper.
  // isRoot makes the InternalRenderer wrapper flex:1; stretch:true makes the
  // component view (Column/Row/etc.) also flex:1. Children are rendered with
  // their original componentData — stretch on leaf/form types is intentionally
  // ignored for wrapper sizing (see FLEX_FILL_TYPES in InternalRenderer).
  const rootType = Object.keys(componentData.component)[0];
  const rootProps = componentData.component[rootType] || {};
  const nextRootProps = {
    ...rootProps,
    ...(!naturalRoot && !preserveRootStretch && rootProps.stretch !== true ? { stretch: true } : {}),
    ...(naturalRoot ? { stretch: false } : {}),
    ...(centerRootContent && rootType === 'Column' ? { align: 'center' } : {}),
  };
  const rootComponentData = {
    ...componentData,
    component: { [rootType]: nextRootProps },
  };

  return (
    <View style={naturalRoot ? styles.rootNatural : styles.root}>
      <InternalRenderer
        componentData={rootComponentData}
        isRoot={!naturalRoot}
        surfaceId={surfaceId}
        surfaces={surfaces}
        dataModel={dataModel}
        stateModel={stateModel}
        sendAction={sendAction}
        setInput={setInput}
        componentId={resolvedComponentId}
        userRole={userRole}
        userPermissions={userPermissions}
        pendingActions={pendingActions}
        backgroundTasks={backgroundTasks}
        jwt={jwt}
        item={item}
        insideNaturalScroll={insideNaturalScroll || naturalRoot}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    width: '100%',
  },
  rootNatural: {
    width: '100%',
  },
  unknown: {
    padding: 10,
    backgroundColor: '#2A1216',
    borderWidth: 1,
    borderColor: '#F85149',
    margin: 5,
    borderRadius: 6,
  },
  loading: {
    flex: 1,
    padding: 40,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  muted: {
    color: '#6E7681',
    fontSize: 12,
  },
});
