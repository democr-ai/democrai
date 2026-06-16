import React from 'react';
import { ImageBackground, Text, TouchableOpacity, View, StyleSheet, ScrollView, ViewStyle } from 'react-native';
import { numberOrDefault, useResponsiveStyle } from '../../../utils/responsive';
import { emitActionSpec, getLiteral } from '../../shared';
import { resolveActiveValue } from '../../rules';
import { authHeadersForMediaUrl, resolveMediaUrl } from '../../../utils/media';
import { Icon } from '../../../components/a2ui/Icon';

const computePadding = (padding: any): ViewStyle => {
  if (!Array.isArray(padding) || padding.length !== 4) return {};
  return {
    paddingTop: numberOrDefault(padding[0], 14),
    paddingRight: numberOrDefault(padding[1], 14),
    paddingBottom: numberOrDefault(padding[2], 14),
    paddingLeft: numberOrDefault(padding[3], 14),
  };
};

const moduleNameFromState = (stateModel: any): string => {
  const rawPath = String(stateModel?.current_path || stateModel?.currentPath || '').trim();
  const firstSegment = rawPath.replace(/^\/+/, '').split('/').filter(Boolean)[0];
  return firstSegment || 'dashboard';
};

const isSuperRole = (role: any): boolean => {
  const normalized = String(role || '').trim().toLowerCase();
  return normalized === 'super' || normalized === 'admin';
};

const normalizePermissions = (value: any): string[] => (
  Array.isArray(value) ? value.map((entry) => String(entry)).filter(Boolean) : []
);

const hasActionAccess = (actionDef: any, userRole: any, userPermissions: any): boolean => {
  const required = actionDef?.required_permissions
    ?? actionDef?.permissions
    ?? actionDef?.check_permission
    ?? actionDef?.check_permissions;
  const requiredList = Array.isArray(required) ? required : required ? [required] : [];
  if (!requiredList.length) return true;
  if (isSuperRole(userRole)) return true;
  const permissions = normalizePermissions(userPermissions);
  return requiredList.some((entry) => permissions.includes(String(entry)));
};

const isActionVisible = (actionDef: any, stateModel: any, item: any, userRole: any, userPermissions: any): boolean => {
  if (!actionDef || typeof actionDef !== 'object') return true;
  if (!hasActionAccess(actionDef, userRole, userPermissions)) return false;
  if (actionDef.show_if !== undefined && !resolveActiveValue(actionDef.show_if, { stateModel, item })) return false;
  if (actionDef.hide_if !== undefined && resolveActiveValue(actionDef.hide_if, { stateModel, item })) return false;
  return true;
};

const actionVariantStyle = (variant: any) => {
  const normalized = String(variant || 'ghost').trim().toLowerCase();
  if (normalized === 'primary' || normalized === 'default') return styles.actionPrimary;
  if (normalized === 'secondary') return styles.actionSecondary;
  if (normalized === 'danger' || normalized === 'destructive') return styles.actionDanger;
  if (normalized === 'outline') return styles.actionOutline;
  return styles.actionGhost;
};

const actionTextStyle = (variant: any) => {
  const normalized = String(variant || 'ghost').trim().toLowerCase();
  if (normalized === 'primary' || normalized === 'default' || normalized === 'danger' || normalized === 'destructive') {
    return styles.actionTextOnFill;
  }
  return styles.actionText;
};

const CardActions: React.FC<{
  actions: any[];
  data: any;
  stateModel: any;
  onAction?: (name: string, ctx: any) => void;
  userRole: any;
  userPermissions: any;
  background?: boolean;
}> = ({ actions, data, stateModel, onAction, userRole, userPermissions, background }) => {
  const itemData = data && typeof data === 'object' ? data : {};
  const visibleActions = Array.isArray(actions)
    ? actions.filter((entry) => isActionVisible(entry, stateModel, itemData, userRole, userPermissions))
    : [];
  if (!visibleActions.length) return null;
  return (
    <View style={[styles.actionsFooter, background && styles.actionsFooterOnBackground]}>
      {visibleActions.map((entry: any, index: number) => {
        const label = getLiteral(entry?.label, 'Action');
        return (
          <TouchableOpacity
            key={`card_action_${index}`}
            style={[styles.actionButton, actionVariantStyle(entry?.variant)]}
            onPress={() => emitActionSpec(entry?.action, onAction, itemData)}
            activeOpacity={0.75}
          >
            {entry?.icon ? <Icon name={entry.icon} size={16} color={actionTextStyle(entry?.variant).color as string} /> : null}
            {label ? <Text style={actionTextStyle(entry?.variant)} numberOfLines={1}>{label}</Text> : null}
          </TouchableOpacity>
        );
      })}
    </View>
  );
};

export const Card: React.FC<any> = ({
  ExplicitList,
  style,
  variant,
  itemActions,
  item_actions,
  actions,
  data,
  onAction,
  background_image,
  backgroundImage,
  padding,
  max_width,
  maxWidth,
  stateModel,
  userRole,
  userPermissions,
  jwt,
}) => {
  const responsiveStyle = useResponsiveStyle(style as ViewStyle);
  const rawBackgroundImage = getLiteral(background_image || backgroundImage, '').trim();
  const resolvedBackgroundImage = rawBackgroundImage
    ? resolveMediaUrl(rawBackgroundImage, moduleNameFromState(stateModel))
    : '';
  const headers = resolvedBackgroundImage ? authHeadersForMediaUrl(resolvedBackgroundImage, jwt) : undefined;
  const resolvedMaxWidth = Number(max_width ?? maxWidth ?? 0);
  const variantName = String(variant || '').toLowerCase();
  const cardStyle: ViewStyle = {
    ...(responsiveStyle as ViewStyle),
    ...(Number.isFinite(resolvedMaxWidth) && resolvedMaxWidth > 0 ? { maxWidth: resolvedMaxWidth } : {}),
  };
  const contentStyle = computePadding(padding);
  const resolvedActions = Array.isArray(itemActions)
    ? itemActions
    : Array.isArray(item_actions)
      ? item_actions
      : Array.isArray(actions)
        ? actions
        : [];
  const variantStyle =
    variantName === 'flat'
      ? styles.flatCard
      : variantName === 'elevated'
        ? styles.elevatedCard
        : null;
  if (resolvedBackgroundImage) {
    return (
      <ImageBackground
        source={headers ? { uri: resolvedBackgroundImage, headers } : { uri: resolvedBackgroundImage }}
        resizeMode="cover"
        style={[styles.card, styles.backgroundCard, variantStyle, cardStyle]}
        imageStyle={styles.backgroundImage}
      >
        <View style={styles.backgroundOverlay} />
        <View style={[styles.backgroundContent, contentStyle]}>
          {ExplicitList}
        </View>
        <CardActions
          actions={resolvedActions}
          data={data}
          stateModel={stateModel}
          onAction={onAction}
          userRole={userRole}
          userPermissions={userPermissions}
          background
        />
      </ImageBackground>
    );
  }

  return (
    <View style={[styles.card, variantStyle, contentStyle, cardStyle]}>
      {ExplicitList}
      <CardActions
        actions={resolvedActions}
        data={data}
        stateModel={stateModel}
        onAction={onAction}
        userRole={userRole}
        userPermissions={userPermissions}
      />
    </View>
  );
};

export const ScrollArea: React.FC<any> = ({ ExplicitList, style, scroll_x, scrollX, scroll_y, scrollY, insideNaturalScroll }) => {
  const responsiveStyle = useResponsiveStyle(style as ViewStyle, { clampFixedWidth: true });
  const wantsHorizontalScroll = scroll_x === true || scrollX === true || String(scroll_x || scrollX || '').toLowerCase() === 'true';
  const wantsVerticalScroll = scroll_y === true || scrollY === true || String(scroll_y || scrollY || '').toLowerCase() === 'true';
  const directChildren = React.Children.toArray(ExplicitList);
  const hostsOwnVerticalScroll = directChildren.length === 1 && directChildren.some((child: any) => {
    const componentData = child?.props?.componentData;
    const type = Object.keys(componentData?.component || {})[0];
    return type === 'MessageList';
  });

  if ((insideNaturalScroll || hostsOwnVerticalScroll) && wantsVerticalScroll && !wantsHorizontalScroll) {
    return (
      <View style={[styles.scrollOwnedArea, responsiveStyle as ViewStyle]}>
        {ExplicitList}
      </View>
    );
  }
  if (insideNaturalScroll && wantsHorizontalScroll) {
    return (
      <ScrollView
        horizontal
        style={[styles.naturalScrollArea, responsiveStyle as ViewStyle]}
        contentContainerStyle={styles.horizontalScrollContent}
        keyboardShouldPersistTaps="handled"
        directionalLockEnabled
      >
        {ExplicitList}
      </ScrollView>
    );
  }
  return (
    <ScrollView
      style={[{ flex: 1, width: '100%' }, responsiveStyle as ViewStyle]}
      contentContainerStyle={styles.scrollContent}
      keyboardShouldPersistTaps="handled"
    >
      {ExplicitList}
    </ScrollView>
  );
};

export const ContentArea: React.FC<any> = ({ ExplicitList, style }) => {
  const responsiveStyle = useResponsiveStyle(style as ViewStyle, { clampFixedWidth: true });
  return (
    <View style={[styles.contentArea, responsiveStyle as ViewStyle]}>
      {ExplicitList}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    width: '100%',
    maxWidth: '100%',
    minWidth: 0,
    backgroundColor: '#1C2128',
    borderRadius: 8,
    padding: 14,
    marginVertical: 6,
    borderWidth: 1,
    borderColor: '#30363D',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  flatCard: {
    backgroundColor: '#161B22',
    shadowOpacity: 0,
    elevation: 0,
  },
  elevatedCard: {
    backgroundColor: '#1C2128',
    shadowOpacity: 0.35,
    elevation: 6,
  },
  backgroundCard: {
    minHeight: 190,
    padding: 0,
    backgroundColor: '#0D1117',
  },
  backgroundImage: {
    borderRadius: 8,
  },
  backgroundOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(13,17,23,0.56)',
  },
  backgroundContent: {
    width: '100%',
    minHeight: 190,
    justifyContent: 'flex-end',
  },
  actionsFooter: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 12,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#30363D',
  },
  actionsFooterOnBackground: {
    marginTop: 0,
    paddingHorizontal: 12,
    paddingBottom: 12,
    backgroundColor: 'rgba(13,17,23,0.68)',
  },
  actionButton: {
    minHeight: 34,
    minWidth: 72,
    maxWidth: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRadius: 7,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderWidth: 1,
  },
  actionPrimary: {
    backgroundColor: '#1F6FEB',
    borderColor: '#388BFD',
  },
  actionSecondary: {
    backgroundColor: '#21262D',
    borderColor: '#30363D',
  },
  actionDanger: {
    backgroundColor: '#DA3633',
    borderColor: '#F85149',
  },
  actionOutline: {
    backgroundColor: 'transparent',
    borderColor: '#58A6FF',
  },
  actionGhost: {
    backgroundColor: 'transparent',
    borderColor: '#30363D',
  },
  actionText: {
    color: '#58A6FF',
    fontSize: 12,
    fontWeight: '700',
    flexShrink: 1,
  },
  actionTextOnFill: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
    flexShrink: 1,
  },
  scrollArea: {
    flex: 1,
  },
  scrollContent: {
    width: '100%',
    minWidth: 0,
    flexGrow: 1,
    paddingBottom: 16,
  },
  naturalScrollArea: {
    width: '100%',
    minWidth: 0,
  },
  scrollOwnedArea: {
    flex: 1,
    width: '100%',
    minWidth: 0,
    minHeight: 0,
  },
  horizontalScrollContent: {
    minWidth: '100%',
    paddingBottom: 16,
  },
  contentArea: {
    flex: 1,
    width: '100%',
    maxWidth: '100%',
    minHeight: 0,
    minWidth: 0,
    overflow: 'hidden',
  },
});
