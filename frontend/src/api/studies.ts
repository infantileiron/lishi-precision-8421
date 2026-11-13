import {request} from './client';import type {Study,StudyRevision} from '../types/entities';
export const list=()=>request<Study[]>('/studies');export const create=(data:unknown)=>request<Study>('/studies','POST',data);
export const revisions=(id:string)=>request<StudyRevision[]>('/studies/'+id+'/revisions');
export const revise=(id:string,data:unknown)=>request<Study>('/studies/'+id+'/revisions','POST',data);
