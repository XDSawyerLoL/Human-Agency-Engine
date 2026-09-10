import express from 'express';
import { installProvidenceExtensions } from './providence_extensions.js';
import { installCryptoMarketRoutes } from './crypto_market_routes.js';

const originalGet=express.application.get;
express.application.get=function(path,...handlers){
  if(path==='/{*path}'&&!this.__providenceExtensionsInstalled){
    installCryptoMarketRoutes(this);
    installProvidenceExtensions(this);
  }
  return originalGet.call(this,path,...handlers);
};
