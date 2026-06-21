import 'punycode';
import { LogBox } from 'react-native';
import { registerRootComponent } from 'expo';

import App from './App';

// Hide on-screen dev warning/error overlays (LogBox) so they don't appear in
// demo recordings. Console logging is unaffected.
LogBox.ignoreAllLogs(true);

// registerRootComponent calls AppRegistry.registerComponent('main', () => App);
// It also ensures that whether you load the app in Expo Go or in a native build,
// the environment is set up appropriately
registerRootComponent(App);
