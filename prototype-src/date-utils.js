const scheduleDate = value => new Date(value + 'T12:00:00Z');
const scheduleISO = date => date.toISOString().slice(0, 10);
const scheduleAdd = (value, days) => {const date=scheduleDate(value);date.setUTCDate(date.getUTCDate()+days);return scheduleISO(date);};
const scheduleMonday = value => scheduleAdd(value,-((scheduleDate(value).getUTCDay()+6)%7));
const scheduleLabel = (value, options={day:'numeric',month:'long'}) => scheduleDate(value).toLocaleDateString('ru-RU',{...options,timeZone:'UTC'});
const scheduleValid = value => /^\d{4}-\d{2}-\d{2}$/.test(value||'') && !Number.isNaN(scheduleDate(value).getTime()) && scheduleISO(scheduleDate(value))===value;
