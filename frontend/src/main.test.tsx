import React from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {App} from './main';

afterEach(()=>{cleanup();vi.restoreAllMocks();});
beforeEach(()=>{sessionStorage.clear()});
const reply=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});

describe('dashboard API integration with mocked responses',()=>{
 it('keeps an invalid token on the login screen',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(reply({detail:'Invalid token'},401)));
  render(<App/>);const user=userEvent.setup();
  await user.type(screen.getByPlaceholderText('Enter your token'),'wrong-token');
  await user.click(screen.getByRole('button',{name:/Open workspace/}));
  expect((await screen.findByRole('alert')).textContent).toContain('Invalid token');
  expect(sessionStorage.getItem('sx_token')).toBeNull();
 });
 it('authenticates and loads lead and review data',async()=>{
  const fetchMock=vi.fn(async (url:string,opts?:RequestInit)=>{
   if(url==='/api/session') {expect((opts?.headers as Record<string,string>).Authorization).toBe('Bearer test-token');return reply({authenticated:true})}
   if(url.startsWith('/api/leads?'))return reply([{id:'1',name:'Test business',website:'https://example.com',domain:'example.com',industry:'Retail',location:'London',source:'Manual',created_at:'2025-01-01',researched_at:null,report:null}]);
   if(url==='/api/duplicate-reviews'||url==='/api/import-batches')return reply([]);
   throw new Error('Unexpected request '+url);
  });
  vi.stubGlobal('fetch',fetchMock);
  render(<App/>);const user=userEvent.setup();
  await user.type(screen.getByPlaceholderText('Enter your token'),'test-token');
  await user.click(screen.getByRole('button',{name:/Open workspace/}));
  expect(await screen.findByText('Test business')).toBeTruthy();
  expect(sessionStorage.getItem('sx_token')).toBe('test-token');
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith('/api/duplicate-reviews',expect.anything()));
 });
 it('sends an explicit matched business for a branch decision',async()=>{
  sessionStorage.setItem('sx_token','test-token');
  const review={id:'review-1',incoming:{name:'Clinic',website:'https://clinic.example',location:'Leeds',industry:'Health',source:'Directory'},matches:[{business_id:'business-1',name:'Clinic',location:'York',domain:'clinic.example',reasons:['same_domain']}],classification:'possible',status:'pending',resolution:null,resolution_history:[]};
  const fetchMock=vi.fn(async (url:string,opts?:RequestInit)=>{
   if(url.startsWith('/api/leads?'))return reply([]);
   if(url==='/api/duplicate-reviews')return reply([review]);
   if(url==='/api/import-batches')return reply([]);
   if(url==='/api/duplicate-reviews/review-1/resolve'){
    expect(JSON.parse(String(opts?.body))).toEqual({decision:'separate_branch',matched_business_id:'business-1'});
    return reply({...review,status:'branch'});
   }
   throw new Error('Unexpected request '+url);
  });vi.stubGlobal('fetch',fetchMock);
  render(<App/>);const user=userEvent.setup();
  await user.click(await screen.findByRole('button',{name:/Review duplicates/}));
  expect(await screen.findByText(/Possible match/)).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'Separate branch'}));
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith('/api/duplicate-reviews/review-1/resolve',expect.anything()));
 });
 it('shows retained import candidates and original CSV',async()=>{
  sessionStorage.setItem('sx_token','test-token');
  const fetchMock=vi.fn(async (url:string)=>{
   if(url.startsWith('/api/leads?')||url==='/api/duplicate-reviews')return reply([]);
   if(url==='/api/import-batches')return reply([{id:'batch-1',created_at:'2025-01-01T00:00:00Z'}]);
   if(url==='/api/import-batches/batch-1')return reply({id:'batch-1',created_at:'2025-01-01T00:00:00Z',original_csv:'name\nExample',candidates:[{id:'row-1',row_number:2,status:'review',raw_data:{name:'Example'},error:''}]});
   return reply([]);
  });vi.stubGlobal('fetch',fetchMock);
  render(<App/>);const user=userEvent.setup();
  await user.click(await screen.findByRole('button',{name:'Import history'}));
  await user.click(await screen.findByRole('button',{name:'View batch'}));
  expect(await screen.findByText('Row 2 · review')).toBeTruthy();
  expect(screen.getByText('name Example')).toBeTruthy();
 });
 it('navigates to Approval Center and displays header',async()=>{
  sessionStorage.setItem('sx_token','test-token');
  const fetchMock=vi.fn(async (url:string)=>{
   if(url==='/api/outreach/messages')return reply([{id:'m-1',business_id:'b-1',business_name:'Zenith Corp',recipient_email:'ceo@zenith.com',subject:'AI Automation Opportunity',body_text:'Hi there',status:'pending_approval',personalization_notes:'Based on workflow gaps'}]);
   return reply([]);
  });vi.stubGlobal('fetch',fetchMock);
  render(<App/>);const user=userEvent.setup();
  await user.click(await screen.findByText(/Approval Center/));
  expect(await screen.findByText(/Email Approval Center/)).toBeTruthy();
  expect(await screen.findByText(/To: ceo@zenith.com/)).toBeTruthy();
 });
});
