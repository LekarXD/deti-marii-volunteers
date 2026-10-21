import type {ComponentType} from 'react';
import {createBrowserRouter,Navigate,Outlet,useLocation,Link} from 'react-router-dom';
import {AppProviders,CandidateLayout,CoordinatorLayout,useSession} from './layouts';
import {PublicLayout} from './PublicLayout';
import {Card} from '../ui';
function page(load:()=>Promise<Record<string,unknown>>,name:string){return async()=>({Component:(await load())[name] as ComponentType});}
const application=(name:string)=>page(()=>import('../features/applications'),name);
const interview=(name:string)=>page(()=>import('../features/interviews'),name);
const learning=(name:string)=>page(()=>import('../features/learning'),name);
const activity=(name:string)=>page(()=>import('../features/activities'),name);
const participant=(name:string)=>page(()=>import('../features/participants'),name);
const crm=(name:string)=>page(()=>import('../features/crm'),name);
const messages=(name:string)=>page(()=>import('../features/messaging'),name);
function StaffBoundary(){const {session}=useSession();const location=useLocation();return session?.is_staff?<Outlet/>:<Navigate to={'/login?next='+encodeURIComponent(location.pathname+location.search)} replace/>;}
async function entry(){const {ApplicationEntryPage}=await import('../features/applications/ApplicationEntryPage');return {Component:function Entry(){const {session}=useSession();return session?.is_staff?<Navigate to="/fund" replace/>:<ApplicationEntryPage/>;}};}
function NotFound(){return <Card><h1 className="h1">Страница не найдена</h1><Link className="btn btn-primary" to="/">На главную</Link></Card>;}
function LegacyGroup(){const location=useLocation();return <Navigate to={'/me/group'+location.search} replace/>;}
export const router=createBrowserRouter([{
 element:<AppProviders><Outlet/></AppProviders>,children:[
  {index:true,lazy:entry},
  {element:<PublicLayout/>,children:[{path:'apply',lazy:application('ApplyPage')},{path:'login',lazy:page(()=>import('../features/auth'),'LoginPage')}]},
  {element:<CandidateLayout/>,children:[
   {path:'application',lazy:application('ApplicationPage')},
   {path:'application/edit',lazy:application('ApplyPage')},
   {path:'onboarding',lazy:learning('OnboardingPage')},
   {path:'onboarding/cards',lazy:learning('OnboardingCardsPage')},
   {path:'onboarding/list',lazy:learning('OnboardingListPage')},
   {path:'interviews',lazy:interview('CandidateInterviewsPage')},
   {path:'academy',lazy:learning('AcademyPage')},
   {path:'academy/lessons/:id',lazy:learning('LessonPage')},
   {path:'messages',lazy:messages('CandidateMessagesPage')},
   {path:'studio-preview',lazy:page(()=>import('../ui/studio'),'StudioPreviewFixture')},
   {path:'opportunities',lazy:activity('OpportunitiesPage')},
   {path:'opportunities/:id',lazy:activity('OpportunityPage')},
   {path:'my/assignments',lazy:activity('MyAssignmentsPage')},
   {path:'my/assignments/:id',lazy:activity('AssignmentPage')},
   {path:'me/group',lazy:participant('GroupPage')},
   {path:'ui',lazy:page(()=>import('../ui/FoundationPreview'),'FoundationPreview')},
  ]},
  {element:<StaffBoundary/>,children:[{path:'fund',element:<CoordinatorLayout/>,children:[
   {index:true,lazy:page(()=>import('./OverviewPage'),'OverviewPage')},
   {path:'candidates',lazy:application('CandidatesPage')},
   {path:'candidates/:id',lazy:application('CandidateDetailPage')},
   {path:'interviews',lazy:interview('InterviewsPage')},
   {path:'interviews/availability',lazy:interview('AvailabilityPage')},
   {path:'volunteers',lazy:crm('VolunteersPage')},
   {path:'volunteers/:id',lazy:crm('VolunteerRecordPage')},
   {path:'contacts/review',lazy:crm('ReservePage')},
   {path:'contacts/import',lazy:crm('CrmImportPage')},
   {path:'roles',lazy:activity('RolesPage')},
   {path:'responses',lazy:activity('StaffResponsesPage')},
   {path:'schedule',lazy:activity('CalendarPage')},
   {path:'events/:id',lazy:activity('EventPage')},
   {path:'messages',lazy:messages('CoordinatorMessagesPage')},
   {path:'learning',lazy:learning('BuilderPage')},
   {path:'learning/lessons/:id',lazy:learning('BuilderLessonPage')},
   {path:'opportunities',lazy:activity('StaffOpportunitiesPage')},
   {path:'participants',lazy:participant('ParticipantsPage')},
   {path:'groups',lazy:participant('GroupsPage')},
  ]}]},
  {path:'group',element:<LegacyGroup/>},
  {path:'coord/interviews',element:<Navigate to="/fund/interviews" replace/>},
  {path:'coord/interviews/availability',element:<Navigate to="/fund/interviews/availability" replace/>},
  {path:'coord/candidates',element:<Navigate to="/fund/candidates" replace/>},
  {path:'*',element:<PublicLayout/>,children:[{path:'*',element:<NotFound/>}]},
 ]}]);
