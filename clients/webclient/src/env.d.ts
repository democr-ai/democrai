export {};

declare global {
  interface Window {
    __CFG__: {
      base_server_http_url: string;
      base_server_ws_url: string;
    };
  }
}
