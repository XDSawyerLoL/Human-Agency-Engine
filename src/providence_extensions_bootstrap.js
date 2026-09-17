import express from 'express';
import { installProvidenceExtensions } from './providence_extensions.js';
import { installCryptoMarketRoutes } from './crypto_market_routes.js';
import { installQuanticPortalStatusRoute } from './quantic_portal_status.js';

const originalGet=express.application.get;
express.application.get=function(path,...handlers){
  if(path==='/{*path}'&&!this.__providenceExtensionsInstalled){
    installQuanticPortalStatusRoute(this);
    installCryptoMarketRoutes(this);
    installProvidenceExtensions(this);
  }
  return originalGet.call(this,path,...handlers);
};
