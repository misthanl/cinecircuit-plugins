// Unit-test adapter only. Browser contracts exercise the actual Vuetify menu.
export function installSelectStub(vue, config) {
  config.global.components.VSelect=vue.defineComponent({
    inheritAttrs:false,
    props:{modelValue:{},items:{},label:{},disabled:Boolean,variant:{},density:{},hideDetails:{},multiple:Boolean},
    emits:['update:modelValue'],
    setup:(props,{attrs,emit})=>()=>vue.h('label',{},[
      vue.h('span',{},props.label),
      vue.h('select',{...attrs,value:props.multiple?undefined:props.modelValue,multiple:props.multiple,disabled:props.disabled,onChange:event=>emit('update:modelValue',props.multiple?Array.from(event.target.selectedOptions,option=>option.value):event.target.value)},
        (props.items||[]).map(item=>vue.h('option',{value:item.value,selected:props.multiple?props.modelValue?.includes(item.value):undefined},item.title)))
    ])
  });
}
