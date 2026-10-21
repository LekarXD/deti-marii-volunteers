const readRoleDirectory = () => demoRead('role-directory', ROLES.map(r=>({id:r.id,title:r.title,task:r.task,prep:r.prep,certificate:r.certificate,approval:r.approval,archived:false})));
const writeRoleDirectory = roles => demoWrite('role-directory',roles);
const roleDuplicate = (roles,title,id='') => roles.some(r=>r.id!==id&&r.title.trim().toLocaleLowerCase('ru')===title.trim().toLocaleLowerCase('ru'));
