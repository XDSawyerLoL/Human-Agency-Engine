import express from 'express';
import { installProvidenceExtensions } from './providence_extensions.js';

const originalGet=express.application.get;
express.application.get=function(path,...handlers){
  if(path==='/{*path}'&&!this.__providenceExtensionsInstalled)installProvidenceExtensions(this);
  return originalGet.call(this,path,...handlers);
};
