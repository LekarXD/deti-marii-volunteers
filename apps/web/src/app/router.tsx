import {getAppBasePath} from '../basePath';
import type {ComponentType} from 'react';
import {createBrowserRouter,Navigate,Outlet,useLocation,Link} from 'react-router-dom';
import {AppProviders,CandidateLayout,CoordinatorLayout,StudioLayout,useSession} from './layouts';
import {PublicLayout} from './PublicLayout';
import {Card} from '../ui';
function page(load:()=>Promise<Record<string,unknown>>,name:string){return async()=>({Component:(await load())[name] as ComponentType});}
const application=(name:string)=>page(()=>import('../features/applications'),name);
const interview=(name:string)=>page(()=>import('../features/interviews'),name);
const learning=(name:string)=>page(()=>import('../features/learning'),name);
const activity=(name:string)=>page(()=>import('../features/activities'),name);
const participant=(name:string)=>page(()=>import('../features/participants'),name);
const knowledge=(name:string)=>page(()=>import('../features/knowledge'),name);
const profile=(name:string)=>page(()=>import('../features/profile'),name);
const notification=(name:string)=>page(()=>import('../features/notifications'),name);
const simulator=(name:string)=>page(()=>import('../features/simulator'),name);
const followup=(name:string)=>page(()=>import('../features/followups'),name);
const crm=(name:string)=>page(()=>import('../features/crm'),name);
const recording=(name:string)=>page(()=>import('../features/lesson-recording'),name);
const messages=(name:string)=>page(()=>import('../features/messaging'),name);
function StaffBoundary(){const {session}=useSession();const location=useLocation();return session?.is_staff?<Outlet/>:<Navigate to={'/login?next='+encodeURIComponent(location.pathname+location.search)} replace/>;}
async function staffWebinars(){const {WebinarsPage}=await import('../features/studio');return {Component:()=> <WebinarsPage staff/>};}
async function entry(){const {ApplicationEntryPage}=await import('../features/applications/ApplicationEntryPage');return {Component:function Entry(){const {session}=useSession();return session?.is_staff?<Navigate to="/fund" replace/>:session?.mfa_required?<Navigate to="/login?next=%2Ffund" replace/>:session?.user_id?<Navigate to="/home" replace/>:<ApplicationEntryPage/>;}};}
function NotFound(){return <Card><h1 className="h1">Страница не найдена</h1><Link className="btn btn-primary" to="/">На главную</Link></Card>;}
function LegacyGroup(){const location=useLocation();return <Navigate to={'/me/group'+location.search} replace/>;}
export const router=createBrowserRouter([{
 element:<AppProviders><Outlet/></AppProviders>,children:[
  {index:true,lazy:entry},
  {element:<PublicLayout/>,children:[{path:'apply',lazy:application('ApplyPage')},{path:'login',lazy:page(()=>import('../features/auth'),'LoginPage')}]},
  {element:<CandidateLayout/>,children:[
   {path:'profile',lazy:profile('ProfilePage')},
   {path:'hours',lazy:profile('HoursPage')},
   {path:'hours/documents',lazy:profile('CertificatesPage')},
   {path:'home',lazy:page(()=>import('../features/home'),'HomePage')},
   {path:'application',lazy:application('ApplicationPage')},
   {path:'application/edit',lazy:application('ApplyPage')},
   {path:'onboarding',lazy:learning('OnboardingPage')},
   {path:'onboarding/cards',element:<Navigate to="/onboarding" replace/>},
   {path:'onboarding/list',element:<Navigate to="/onboarding" replace/>},
   {path:'interviews',lazy:interview('CandidateInterviewsPage')},
   {path:'academy',lazy:learning('AcademyPage')},
   {path:'academy/lessons/:id',lazy:learning('LessonPage')},
   {path:'simulator',lazy:simulator('SimulatorPage')},
   {path:'simulator/:scenario_id',lazy:simulator('SimulatorPage')},
   {path:'simulator/sessions/:id',lazy:simulator('SimulatorSessionPage')},
   {path:'mentor',lazy:knowledge('MentorPage')},
   {path:'messages',lazy:messages('CandidateMessagesPage')},
   {path:'studio-preview',lazy:page(()=>import('../ui/studio'),'StudioPreviewFixture')},
   {path:'opportunities',lazy:activity('OpportunitiesPage')},
   {path:'opportunities/:id',lazy:activity('OpportunityPage')},
   {path:'my/schedule',lazy:activity('PersonalSchedulePage')},
   {path:'webinars',lazy:page(()=>import('../features/studio'),'WebinarsPage')},
   {path:'my/assignments',lazy:activity('MyAssignmentsPage')},
   {path:'my/assignments/:id',lazy:activity('AssignmentPage')},
   {path:'my/assignments/:id/preparation',lazy:followup('FirstShiftPage')},
   {path:'my/assignments/:id/reflection',lazy:followup('ReflectionPage')},
   {path:'me/group',lazy:participant('GroupPage')},
   {path:'ui',lazy:page(()=>import('../ui/FoundationPreview'),'FoundationPreview')},
  ]},
  {element:<StudioLayout/>,children:[{path:'studio/:sessionId',lazy:page(()=>import('../features/studio'),'LiveRoomPage')}]},
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
   {path:'profile-review',lazy:profile('ProfileReviewPage')},
   {path:'webinars',lazy:staffWebinars},
   {path:'recordings',lazy:recording('RecordingProjectsPage')},
   {path:'recordings/:id',lazy:recording('RecordingProjectPage')},
   {path:'notifications',lazy:notification('NotificationAdminPage')},
   {path:'reports',lazy:page(()=>import('../features/reporting'),'ReportsPage')},
   {path:'integrations/dobro/transfers',lazy:page(()=>import('../features/dobro-transfer'),'DobroTransferPage')},
   {path:'admin',lazy:page(()=>import('../features/admin'),'AdminPage')},
   {path:'scenarios',lazy:simulator('ScenariosPage')},
   {path:'simulator/review',lazy:simulator('SimulatorReviewPage')},
   {path:'signals',lazy:followup('SignalsPage')},
   {path:'knowledge',lazy:knowledge('KnowledgePage')},
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
 ]}],{basename:getAppBasePath()||'/'});
